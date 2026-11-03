"""Логика чата и анализа фото на подставном клиенте. Реальная модель здесь не вызывается."""

import json
from datetime import datetime
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock

from app.config import settings
from app.models import Appointment, AppointmentSource, AppointmentStatus, Conversation, NailAnalysis
from app.routers import ai as ai_router
from app.services import assistant, nails
from app.services.claude import blocks_for_history
from tests.conftest import auth

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def text_block(value):
    return BetaTextBlock(type="text", text=value)


def tool_block(name, params, call_id="call_1"):
    return BetaToolUseBlock(type="tool_use", id=call_id, name=name, input=params)


def reply(content, stop_reason="end_turn"):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


class FakeClaude:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params):
        # Снимок истории: проверка, что отправленное позже только дополняет её
        self.requests.append(json.loads(json.dumps(params, default=str)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def fake(monkeypatch):
    def install(responses):
        client = FakeClaude(responses)
        monkeypatch.setattr(ai_router, "get_claude", lambda: client)
        return client

    return install


def tool_results(request):
    return [b for m in request["messages"] if m["role"] == "user" and isinstance(m["content"], list) for b in m["content"]]


def test_ai_disabled_without_key(client, world):
    response = client.post("/api/ai/chat", json={"message": "Hi"}, headers=auth(world.alice))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ai_not_configured"
    assert client.get("/api/meta").json()["ai_enabled"] is False


def test_chat_requires_login(client, fake):
    fake([])
    assert client.post("/api/ai/chat", json={"message": "Hi"}).status_code == 401


def test_request_shape_uses_expected_model_settings(client, world, fake):
    claude = fake([reply([text_block("Hello")])])
    client.post("/api/ai/chat", json={"message": "Hi", "lang": "tk"}, headers=auth(world.alice))
    request = claude.requests[0]
    assert request["model"] == settings.claude_model
    assert request["fallbacks"] == "default"
    assert request["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in request and "temperature" not in request and "tool_choice" not in request
    assert all(t["strict"] and t["input_schema"]["additionalProperties"] is False for t in request["tools"])
    assert request["messages"][1]["role"] == "system" and "Turkmen" in request["messages"][1]["content"]


def test_full_booking_flow_through_tools(client, world, fake, db):
    start = world.at(11).isoformat()
    claude = fake(
        [
            reply([tool_block("find_available_slots", {"service_id": world.nails.id, "date": world.tomorrow.isoformat(), "master_id": None})], "tool_use"),
            reply([text_block("Записать вас на 11:00?")]),
            reply([tool_block("create_appointment", {"service_id": world.nails.id, "master_id": world.nail_master.id, "starts_at": start, "notes": None})], "tool_use"),
            reply([text_block("Готово!")]),
        ]
    )
    first = client.post("/api/ai/chat", json={"message": "Маникюр завтра"}, headers=auth(world.alice)).json()
    assert first["booked"] is False
    assert [t["text"] for t in first["messages"]] == ["Маникюр завтра", "Записать вас на 11:00?"]
    slots = json.loads(tool_results(claude.requests[1])[0]["content"])["slots"]
    assert any(s["starts_at"] == start for s in slots)

    second = client.post(
        "/api/ai/chat",
        json={"message": "Да", "conversation_id": first["conversation_id"]},
        headers=auth(world.alice),
    ).json()
    assert second["booked"] is True
    appointment = db.query(Appointment).one()
    assert appointment.client_id == world.alice.id
    assert appointment.source == AppointmentSource.chat

    # История только дополняется: каждый запрос начинается с предыдущего
    for earlier, later in zip(claude.requests, claude.requests[1:]):
        assert later["messages"][: len(earlier["messages"])] == earlier["messages"]


def test_booking_conflict_returns_tool_error(client, world, fake, db):
    start = world.at(11)
    db.add(Appointment(client_id=world.bob.id, master_id=world.nail_master.id, service_id=world.nails.id, starts_at=start, ends_at=world.at(12), price=100))
    db.commit()
    claude = fake(
        [
            reply([tool_block("create_appointment", {"service_id": world.nails.id, "master_id": world.nail_master.id, "starts_at": start.isoformat(), "notes": None})], "tool_use"),
            reply([text_block("Это время занято")]),
        ]
    )
    response = client.post("/api/ai/chat", json={"message": "Да"}, headers=auth(world.alice)).json()
    assert response["booked"] is False
    result = tool_results(claude.requests[1])[0]
    assert result["is_error"] is True and "slot_taken" in result["content"]


def test_cannot_cancel_another_clients_appointment(client, world, fake, db):
    other = Appointment(client_id=world.bob.id, master_id=world.nail_master.id, service_id=world.nails.id, starts_at=world.at(11), ends_at=world.at(12), price=100)
    db.add(other)
    db.commit()
    claude = fake(
        [
            reply([tool_block("cancel_appointment", {"appointment_id": other.id})], "tool_use"),
            reply([text_block("Не нашёл такую запись")]),
        ]
    )
    client.post("/api/ai/chat", json={"message": "Отмени"}, headers=auth(world.alice))
    assert tool_results(claude.requests[1])[0]["is_error"] is True
    db.refresh(other)
    assert other.status == AppointmentStatus.booked


def test_cannot_continue_someone_elses_conversation(client, world, fake, db):
    fake([reply([text_block("Hello")])])
    created = client.post("/api/ai/chat", json={"message": "Hi"}, headers=auth(world.alice)).json()
    response = client.post(
        "/api/ai/chat",
        json={"message": "Hi", "conversation_id": created["conversation_id"]},
        headers=auth(world.bob),
    )
    assert response.status_code == 404


def test_parallel_tool_calls_get_one_result_message(client, world, fake):
    claude = fake(
        [
            reply([tool_block("list_services", {}, "a"), tool_block("list_masters", {}, "b")], "tool_use"),
            reply([text_block("ok")]),
        ]
    )
    client.post("/api/ai/chat", json={"message": "Что есть?"}, headers=auth(world.alice))
    last = claude.requests[1]["messages"][-1]
    assert last["role"] == "user"
    assert [b["tool_use_id"] for b in last["content"]] == ["a", "b"]


def test_refusal_and_runaway_loop(client, world, fake):
    fake([reply([], "refusal")])
    response = client.post("/api/ai/chat", json={"message": "x"}, headers=auth(world.alice))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "ai_refused"

    fake([reply([tool_block("list_services", {})], "tool_use") for _ in range(assistant.MAX_TOOL_ROUNDS)])
    response = client.post("/api/ai/chat", json={"message": "x"}, headers=auth(world.alice))
    assert response.status_code == 502


def test_conversation_survives_api_failure(client, world, fake, db):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    fake([anthropic.APIConnectionError(request=request)])
    response = client.post("/api/ai/chat", json={"message": "Привет"}, headers=auth(world.alice))
    assert response.status_code == 503 and response.json()["detail"]["code"] == "ai_connection"
    conversation = db.query(Conversation).one()
    assert conversation.messages[0]["content"] == "Привет"


def test_chat_rate_limit(client, world, fake, monkeypatch):
    monkeypatch.setattr(settings, "chat_limit_per_hour", 1)
    fake([reply([text_block("a")])])
    assert client.post("/api/ai/chat", json={"message": "1"}, headers=auth(world.alice)).status_code == 200
    assert client.post("/api/ai/chat", json={"message": "2"}, headers=auth(world.alice)).status_code == 429


def test_blocks_for_history_drops_model_blocks_before_fallback():
    class Block:
        def __init__(self, **data):
            self.data = data

        def to_dict(self):
            return self.data

    blocks = [
        Block(type="thinking", thinking=""),
        Block(type="text", text="a"),
        Block(type="fallback"),
        Block(type="thinking", thinking=""),
        Block(type="text", text="b"),
    ]
    assert [b["type"] for b in blocks_for_history(blocks)] == ["text", "fallback", "thinking", "text"]


def analysis(**overrides):
    return {
        "is_nail_photo": True,
        "photo_kind": "own_nails",
        "summary": "s",
        "shape": "oval",
        "length": "short",
        "colors": ["red"],
        "finish": "gloss",
        "design_details": [],
        "care_observations": [],
        "see_doctor_note": None,
        "recommendations": [],
        **overrides,
    }


def test_nail_analysis_keeps_only_catalogue_services(client, world, fake, db):
    result = analysis(
        recommendations=[
            {"service_id": world.nails.id, "reason": "ok"},
            {"service_id": world.hair.id, "reason": "not a nail service"},
            {"service_id": 99999, "reason": "made up"},
        ]
    )
    claude = fake([reply([text_block(json.dumps(result))])])
    response = client.post(
        "/api/ai/nails",
        files={"file": ("a.png", PNG, "image/png")},
        data={"lang": "tk"},
        headers=auth(world.alice),
    )
    assert response.status_code == 200
    assert [r["service_id"] for r in response.json()["recommendations"]] == [world.nails.id]
    assert db.query(NailAnalysis).count() == 1

    request = claude.requests[0]
    image, prompt = request["messages"][0]["content"]
    assert image["source"]["media_type"] == "image/png"
    assert "Turkmen" in prompt["text"] and "Dyrnak" in prompt["text"]
    assert request["output_config"]["format"]["schema"] == nails.ANALYSIS_SCHEMA
    assert image["source"]["data"] not in json.dumps(db.query(NailAnalysis).one().result)


@pytest.mark.parametrize(
    ("payload", "status", "error"),
    [
        (b"not an image at all", 415, "image_bad_type"),
        (b"", 415, "image_bad_type"),
        (PNG + b"0" * nails.MAX_IMAGE_BYTES, 413, "image_too_large"),
    ],
)
def test_nail_upload_validation(client, world, fake, payload, status, error):
    fake([])
    response = client.post("/api/ai/nails", files={"file": ("a.png", payload, "image/png")}, headers=auth(world.alice))
    assert response.status_code == status and response.json()["detail"]["code"] == error


def test_nail_schema_meets_strict_requirements():
    def walk(schema):
        if schema.get("type") == "object":
            assert schema["additionalProperties"] is False
            assert set(schema["required"]) == set(schema["properties"])
            for child in schema["properties"].values():
                walk(child)
        if schema.get("type") == "array":
            walk(schema["items"])

    walk(nails.ANALYSIS_SCHEMA)


def test_sdk_accepts_our_message_blocks():
    assert blocks_for_history([text_block("hi")]) == [{"type": "text", "text": "hi"}]


def sdk_client(responses, seen):
    """Настоящий SDK Anthropic с подменой только сетевого транспорта."""

    def handler(request):
        seen.append({"headers": request.headers, "body": json.loads(request.content)})
        return httpx2.Response(200, json=responses.pop(0))

    return anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )


def api_message(content, stop_reason):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": settings.claude_model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def test_real_sdk_round_trip_preserves_blocks(client, world, monkeypatch):
    thinking = {"type": "thinking", "thinking": "", "signature": "sig-abc"}
    seen = []
    responses = [
        api_message([thinking, {"type": "tool_use", "id": "toolu_1", "name": "list_services", "input": {}}], "tool_use"),
        api_message([{"type": "text", "text": "Вот услуги"}], "end_turn"),
    ]
    monkeypatch.setattr(ai_router, "get_claude", lambda: sdk_client(responses, seen))

    response = client.post("/api/ai/chat", json={"message": "Что есть?"}, headers=auth(world.alice))
    assert response.status_code == 200, response.text
    assert response.json()["messages"][-1]["text"] == "Вот услуги"

    first, second = seen
    assert "server-side-fallback-2026-07-01" in first["headers"]["anthropic-beta"]
    assert first["body"]["model"] == settings.claude_model
    assert first["body"]["fallbacks"] == "default"
    # Блок мышления возвращается без изменений вместе с подписью
    assert second["body"]["messages"][2]["content"][0] == thinking
    assert second["body"]["messages"][: 2] == first["body"]["messages"]
    assert second["body"]["messages"][3]["content"][0]["type"] == "tool_result"


def test_real_sdk_nail_structured_output(client, world, monkeypatch):
    seen = []
    result = analysis(recommendations=[{"service_id": world.nails.id, "reason": "ok"}])
    responses = [api_message([{"type": "text", "text": json.dumps(result)}], "end_turn")]
    monkeypatch.setattr(ai_router, "get_claude", lambda: sdk_client(responses, seen))
    response = client.post("/api/ai/nails", files={"file": ("a.png", PNG, "image/png")}, headers=auth(world.alice))
    assert response.status_code == 200, response.text
    assert seen[0]["body"]["output_config"]["format"]["type"] == "json_schema"
    assert seen[0]["body"]["messages"][0]["content"][0]["type"] == "image"
