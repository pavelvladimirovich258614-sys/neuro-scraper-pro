"""Тест throttle-middleware: повторное идентичное нажатие гасится."""

import time
import types
import pytest

from middlewares.throttle_middleware import CallbackThrottleMiddleware, THROTTLE_WINDOW


def make_callback(user_id: int, data: str):
    """Минимальный фейковый CallbackQuery."""
    answered = {"count": 0}

    async def answer(*a, **k):
        answered["count"] += 1

    cq = types.SimpleNamespace(
        from_user=types.SimpleNamespace(id=user_id),
        data=data,
        answer=answer,
        _answered=answered,
    )
    # Чтобы isinstance(event, CallbackQuery) прошёл — патчим проверку через подмену
    return cq


@pytest.fixture
def patched_isinstance(monkeypatch):
    """Подменяем isinstance внутри middleware на распознавание нашего фейка."""
    import middlewares.throttle_middleware as mod
    real_isinstance = isinstance

    def fake(obj, cls):
        if cls is mod.CallbackQuery:
            return hasattr(obj, "data") and hasattr(obj, "from_user")
        return real_isinstance(obj, cls)

    monkeypatch.setattr(mod, "isinstance", fake, raising=False)
    return fake


async def test_duplicate_callback_blocked(patched_isinstance):
    mw = CallbackThrottleMiddleware()
    calls = {"count": 0}

    async def handler(event, data):
        calls["count"] += 1
        return "ok"

    cq = make_callback(1, "same_button")
    # Первый вызов проходит
    assert await mw(handler, cq, {}) == "ok"
    # Второй идентичный сразу же — заблокирован
    assert await mw(handler, cq, {}) is None
    assert calls["count"] == 1


async def test_different_callback_passes(patched_isinstance):
    mw = CallbackThrottleMiddleware()
    calls = {"count": 0}

    async def handler(event, data):
        calls["count"] += 1
        return "ok"

    await mw(handler, make_callback(1, "button_a"), {})
    # Другой callback_data проходит, даже сразу
    await mw(handler, make_callback(1, "button_b"), {})
    assert calls["count"] == 2


async def test_same_callback_after_window_passes(patched_isinstance):
    mw = CallbackThrottleMiddleware()
    calls = {"count": 0}

    async def handler(event, data):
        calls["count"] += 1

    cq = make_callback(1, "btn")
    await mw(handler, cq, {})
    # Эмулируем истечение окна
    mw._last[1] = ("btn", time.time() - THROTTLE_WINDOW - 0.1)
    await mw(handler, cq, {})
    assert calls["count"] == 2
