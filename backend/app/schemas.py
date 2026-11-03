from datetime import date, datetime, time
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field

from app.models import AppointmentSource, AppointmentStatus, Role


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Localized(BaseModel):
    tk: str = Field(min_length=1, max_length=200)
    ru: str = Field(min_length=1, max_length=200)
    en: str = Field(min_length=1, max_length=200)


class LocalizedText(BaseModel):
    tk: str = Field(default="", max_length=1000)
    ru: str = Field(default="", max_length=1000)
    en: str = Field(default="", max_length=1000)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=30)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    phone: str | None
    role: Role


class TokenOut(BaseModel):
    access_token: str
    user: UserOut


class ServiceIn(BaseModel):
    category: str = Field(min_length=1, max_length=30)
    name: Localized
    description: LocalizedText = LocalizedText()
    duration_minutes: int = Field(gt=0, le=600)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    is_active: bool = True


class ServiceOut(ORM):
    id: int
    category: str
    name: dict
    description: dict
    duration_minutes: int
    price: float
    is_active: bool


class HoursIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time


class HoursOut(ORM):
    weekday: int
    start_time: time
    end_time: time


class MasterOut(BaseModel):
    id: int
    full_name: str
    title: dict
    is_active: bool
    service_ids: list[int]
    hours: list[HoursOut]


class MasterCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    title: LocalizedText = LocalizedText()
    service_ids: list[int] = []
    hours: list[HoursIn] = []


class MasterUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    title: LocalizedText
    is_active: bool
    service_ids: list[int]
    hours: list[HoursIn]


class SlotOut(BaseModel):
    master_id: int
    master_name: str
    starts_at: datetime


class AppointmentIn(BaseModel):
    service_id: int
    master_id: int
    starts_at: AwareDatetime
    notes: str | None = Field(default=None, max_length=500)
    # Только для администратора: запись клиента, позвонившего в салон
    client_id: int | None = None


class AppointmentOut(BaseModel):
    id: int
    client_id: int
    client_name: str
    client_phone: str | None
    master_id: int
    master_name: str
    service_id: int
    service_name: dict
    starts_at: datetime
    ends_at: datetime
    price: float
    status: AppointmentStatus
    source: AppointmentSource
    notes: str | None


class StatusUpdate(BaseModel):
    status: AppointmentStatus


class ClientOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str | None
    visits: int
    total_spent: float
    last_visit: datetime | None


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    lang: str = Field(default="ru", pattern="^(tk|ru|en)$")
    conversation_id: int | None = None


class ChatTurnOut(BaseModel):
    role: str
    text: str


class ChatOut(BaseModel):
    conversation_id: int | None
    messages: list[ChatTurnOut]
    booked: bool = False


