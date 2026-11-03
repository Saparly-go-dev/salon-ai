from typing import Annotated

from fastapi import APIRouter, Form, UploadFile
from sqlalchemy import select

from app.config import settings
from app.deps import CurrentUser, Db, api_error, rate_limiter
from app.models import Conversation
from app.schemas import ChatIn, ChatOut
from app.services import assistant, nails
from app.services.claude import get_claude

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/chat/latest", response_model=ChatOut)
def latest_conversation(db: Db, user: CurrentUser):
    conversation = db.scalar(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.id.desc()).limit(1)
    )
    if conversation is None:
        return ChatOut(conversation_id=None, messages=[])
    return ChatOut(conversation_id=conversation.id, messages=assistant.visible_turns(conversation.messages))


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, db: Db, user: CurrentUser):
    client = get_claude()
    rate_limiter.check(f"chat:{user.id}", settings.chat_limit_per_hour, 3600)
    conversation = assistant.get_conversation(db, user, body.conversation_id)
    result = assistant.chat(db, client, user, conversation, body.message, body.lang)
    return ChatOut(
        conversation_id=conversation.id,
        messages=assistant.visible_turns(conversation.messages),
        booked=result["booked"],
    )


@router.post("/nails")
def analyze_nails(file: UploadFile, db: Db, user: CurrentUser, lang: Annotated[str, Form(pattern="^(tk|ru|en)$")] = "ru"):
    client = get_claude()
    rate_limiter.check(f"nails:{user.id}", settings.nail_limit_per_hour, 3600)
    # Читается на байт больше лимита: этого достаточно, чтобы определить превышение
    image = file.file.read(nails.MAX_IMAGE_BYTES + 1)
    if not image:
        raise api_error(415, "image_bad_type")
    return nails.analyze(db, client, user, image, lang)
