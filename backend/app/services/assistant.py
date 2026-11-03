"""Чат-ассистент для записи: цикл Claude с инструментами поверх той же логики, что и REST API."""

import json
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.deps import api_error
from app.models import Appointment, AppointmentSource, AppointmentStatus, Conversation, Master, Service, User
from app.services import booking
from app.services.claude import blocks_for_history, call_claude

MAX_TOOL_ROUNDS = 8
LANGUAGE_NAMES = {"tk": "Turkmen", "ru": "Russian", "en": "English"}

SYSTEM_PROMPT = """You are the booking assistant of a beauty salon. You help clients choose a service, find a free time and manage their appointments, using the tools provided.

Service names, prices, masters and free times come only from the tools, so look them up rather than stating them from memory. Never promise a discount, result or time that the tools do not confirm.

Before calling create_appointment or cancel_appointment, tell the client exactly what will happen (service, master, date, time, price) and wait for their clear agreement in a later message. If they already gave all the details and clearly asked you to book in the same message, one confirmation question is still required. After a booking succeeds, confirm the details in one or two sentences.

When several times are free, offer at most five that match the request. When the client is vague about the date, ask or suggest the nearest suitable days. If a tool returns an error, explain it plainly and offer an alternative.

Keep replies short and friendly, in plain text without Markdown. Reply in the language named in the latest system note unless the client writes in another of the languages Turkmen, Russian or English, in which case follow the client. Only discuss this salon and its services; politely redirect other topics. You act only for the signed-in client and cannot see other clients' data. Do not give medical advice."""

TOOLS = [
    {
        "name": "list_services",
        "description": "List the salon's active services with id, category, name, description, duration in minutes and price. Call this to answer questions about services or prices, or to find a service_id.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "list_masters",
        "description": "List active masters with id, name, specialty and the ids of the services they perform.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "find_available_slots",
        "description": "Find free start times for one service on one date, optionally with one master. Times are in the salon's time zone. An empty result means nothing is free that day.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "service_id": {"type": "integer"},
                "date": {"type": "string", "format": "date", "description": "Date as YYYY-MM-DD"},
                "master_id": {"type": ["integer", "null"], "description": "A specific master, or null for any master"},
            },
            "required": ["service_id", "date", "master_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_appointment",
        "description": "Book an appointment for the signed-in client. Call only after the client has explicitly confirmed the service, master, date and time. Use a start time returned by find_available_slots.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "service_id": {"type": "integer"},
                "master_id": {"type": "integer"},
                "starts_at": {"type": "string", "description": "Start time exactly as returned by find_available_slots"},
                "notes": {"type": ["string", "null"], "description": "Client's wishes for the master, or null"},
            },
            "required": ["service_id", "master_id", "starts_at", "notes"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_my_appointments",
        "description": "List the signed-in client's upcoming appointments.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel one of the signed-in client's upcoming appointments. Call only after the client has explicitly confirmed the cancellation.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"appointment_id": {"type": "integer"}},
            "required": ["appointment_id"],
            "additionalProperties": False,
        },
    },
]


class ToolError(Exception):
    pass


def _localized(value: dict, lang: str) -> str:
    return value.get(lang) or value.get("ru") or next(iter(value.values()), "")


def _parse_start(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ToolError("starts_at is not a valid ISO datetime") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=settings.tz)


def _appointment_info(appointment: Appointment, lang: str) -> dict:
    return {
        "appointment_id": appointment.id,
        "service": _localized(appointment.service.name, lang),
        "master": appointment.master.user.full_name,
        "starts_at": appointment.starts_at.astimezone(settings.tz).isoformat(),
        "price": float(appointment.price),
        "currency": settings.salon_currency,
        "status": appointment.status.value,
    }


class ToolExecutor:
    """Выполняет вызовы модели. Клиент берётся из сессии, а не из параметров инструмента,
    поэтому модель не может действовать от имени другого пользователя."""

    def __init__(self, db: Session, user: User, lang: str):
        self.db = db
        self.user = user
        self.lang = lang
        self.booked = False

    def run(self, name: str, params: dict) -> str:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            raise ToolError(f"Unknown tool: {name}")
        try:
            return json.dumps(handler(**params), ensure_ascii=False)
        except TypeError as exc:
            raise ToolError(f"Invalid arguments for {name}") from exc

    def _tool_list_services(self) -> list[dict]:
        services = self.db.scalars(select(Service).where(Service.is_active).order_by(Service.category, Service.id))
        return [
            {
                "id": s.id,
                "category": s.category,
                "name": _localized(s.name, self.lang),
                "description": _localized(s.description, self.lang),
                "duration_minutes": s.duration_minutes,
                "price": float(s.price),
                "currency": settings.salon_currency,
            }
            for s in services
        ]

    def _tool_list_masters(self) -> list[dict]:
        masters = self.db.scalars(
            select(Master)
            .where(Master.is_active)
            .options(selectinload(Master.user), selectinload(Master.services))
            .order_by(Master.id)
        )
        return [
            {
                "id": m.id,
                "name": m.user.full_name,
                "specialty": _localized(m.title, self.lang),
                "service_ids": [s.id for s in m.services],
            }
            for m in masters
        ]

    def _tool_find_available_slots(self, service_id: int, date: str, master_id: int | None) -> dict:
        service = self.db.get(Service, service_id)
        if service is None or not service.is_active:
            raise ToolError("Service not found")
        try:
            on_date = _date_from(date)
        except ValueError as exc:
            raise ToolError("date must be YYYY-MM-DD") from exc
        slots = booking.available_slots(self.db, service, on_date, master_id)
        return {
            "date": date,
            "slots": [
                {
                    "master_id": s.master_id,
                    "master": s.master_name,
                    "starts_at": s.starts_at.astimezone(settings.tz).isoformat(),
                }
                for s in slots
            ],
        }

    def _tool_create_appointment(self, service_id: int, master_id: int, starts_at: str, notes: str | None) -> dict:
        try:
            appointment = booking.create_appointment(
                self.db,
                self.user.id,
                service_id,
                master_id,
                _parse_start(starts_at),
                notes,
                AppointmentSource.chat,
            )
        except booking.BookingError as exc:
            raise ToolError(f"Booking failed: {exc.code}") from exc
        self.booked = True
        return {"booked": True, **_appointment_info(appointment, self.lang)}

    def _tool_list_my_appointments(self) -> list[dict]:
        appointments = self.db.scalars(
            select(Appointment)
            .where(
                Appointment.client_id == self.user.id,
                Appointment.status == AppointmentStatus.booked,
                Appointment.starts_at >= datetime.now(settings.tz),
            )
            .order_by(Appointment.starts_at)
        )
        return [_appointment_info(a, self.lang) for a in appointments]

    def _tool_cancel_appointment(self, appointment_id: int) -> dict:
        appointment = self.db.get(Appointment, appointment_id)
        if appointment is None or appointment.client_id != self.user.id:
            raise ToolError("Appointment not found among this client's appointments")
        try:
            booking.cancel_appointment(self.db, appointment)
        except booking.BookingError as exc:
            raise ToolError(f"Cancellation failed: {exc.code}") from exc
        return {"cancelled": True, **_appointment_info(appointment, self.lang)}


def _date_from(value: str) -> date:
    return date.fromisoformat(value)


def _context_note(lang: str) -> str:
    now = datetime.now(settings.tz)
    return (
        f"Current salon time: {now:%A, %Y-%m-%d %H:%M} ({settings.salon_timezone}). "
        f"The client's interface language is {LANGUAGE_NAMES[lang]}."
    )


def _save(db: Session, conversation: Conversation) -> None:
    flag_modified(conversation, "messages")
    db.commit()


def get_conversation(db: Session, user: User, conversation_id: int | None) -> Conversation:
    if conversation_id is not None:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None or conversation.user_id != user.id:
            raise api_error(404, "conversation_not_found")
        return conversation
    conversation = Conversation(user_id=user.id, messages=[])
    db.add(conversation)
    db.flush()
    return conversation


def visible_turns(messages: list[dict]) -> list[dict]:
    """Только то, что видит клиент: реплики без системных заметок и служебных блоков."""
    turns = []
    for message in messages:
        content = message["content"]
        if message["role"] == "user" and isinstance(content, str):
            turns.append({"role": "user", "text": content})
        elif message["role"] == "assistant" and isinstance(content, list):
            text = "\n".join(b["text"] for b in content if b.get("type") == "text").strip()
            if text:
                turns.append({"role": "assistant", "text": text})
    return turns


def chat(db: Session, client, user: User, conversation: Conversation, text: str, lang: str) -> dict:
    executor = ToolExecutor(db, user, lang)
    # Новая JSON-структура на каждый шаг: история только дополняется
    conversation.messages = [
        *conversation.messages,
        {"role": "user", "content": text},
        {"role": "system", "content": _context_note(lang)},
    ]
    _save(db, conversation)

    for _ in range(MAX_TOOL_ROUNDS):
        response = call_claude(
            client,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},
            messages=conversation.messages,
        )
        if response.stop_reason == "refusal":
            raise api_error(422, "ai_refused")
        if response.stop_reason == "max_tokens":
            raise api_error(502, "ai_error")

        assistant_message = {"role": "assistant", "content": blocks_for_history(response.content)}
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_calls:
            conversation.messages = [*conversation.messages, assistant_message]
            _save(db, conversation)
            return {"booked": executor.booked}

        results = []
        for call in tool_calls:
            try:
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": executor.run(call.name, call.input)})
            except ToolError as exc:
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": str(exc), "is_error": True})
        # Запрос и результаты сохраняются вместе: если следующий вызов API упадёт,
        # история останется корректной, а созданная запись не потеряется
        conversation.messages = [*conversation.messages, assistant_message, {"role": "user", "content": results}]
        _save(db, conversation)

    raise api_error(502, "ai_error")
