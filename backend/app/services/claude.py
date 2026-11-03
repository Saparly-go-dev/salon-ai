"""Общая настройка клиента Claude и преобразование ошибок API в коды для интерфейса."""

import anthropic

from app.config import settings
from app.deps import api_error

# При отказе классификаторов безопасности API сам повторяет запрос на рекомендованной модели
BETAS = ["server-side-fallback-2026-07-01"]
FALLBACKS = "default"


def get_claude() -> anthropic.Anthropic:
    if not settings.ai_enabled:
        raise api_error(503, "ai_not_configured")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=120.0)


def call_claude(client: anthropic.Anthropic, **params):
    try:
        return client.beta.messages.create(
            model=settings.claude_model,
            betas=BETAS,
            fallbacks=FALLBACKS,
            **params,
        )
    except anthropic.AuthenticationError as exc:
        raise api_error(503, "ai_auth_failed") from exc
    except anthropic.RateLimitError as exc:
        raise api_error(503, "ai_busy") from exc
    except anthropic.APIStatusError as exc:
        raise api_error(502, "ai_error") from exc
    except anthropic.APIConnectionError as exc:
        raise api_error(503, "ai_connection") from exc


MODEL_ONLY_BLOCKS = {"thinking", "redacted_thinking", "tool_use"}


def blocks_for_history(content: list) -> list[dict]:
    """Блоки ответа для следующего запроса.

    Если модель сменилась посреди ответа, служебные блоки до последней границы `fallback`
    обратно не передаются. Всё остальное сохраняется без изменений.
    """
    blocks = [block.to_dict() for block in content]
    boundary = max((i for i, b in enumerate(blocks) if b["type"] == "fallback"), default=-1)
    return [b for i, b in enumerate(blocks) if i > boundary or b["type"] not in MODEL_ONLY_BLOCKS]
