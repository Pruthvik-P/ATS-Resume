from __future__ import annotations

from app.core.config import settings
from app.services.jd_cache import analyse_jd_cached, cache_size, reset_jd_cache


async def test_jd_cache_hits_for_identical_input(monkeypatch):
    reset_jd_cache()
    text = "Requirements\n- Python and FastAPI required\n- Kubernetes preferred"
    analysis, _, hit = await analyse_jd_cached(text, title="Backend")
    assert hit is False
    assert analysis.title == "Backend"
    again, _, second_hit = await analyse_jd_cached(text, title="Backend")
    assert second_hit is True
    assert again.title == "Backend"
    assert cache_size() == 1


async def test_jd_cache_misses_for_different_input(monkeypatch):
    reset_jd_cache()
    await analyse_jd_cached("Requirements\n- Python required", title="A")
    _, _, hit = await analyse_jd_cached("Requirements\n- Go required", title="B")
    assert hit is False
    assert cache_size() == 2


async def test_jd_cache_redis_failure_falls_back_to_memory(monkeypatch):
    reset_jd_cache()
    monkeypatch.setattr(settings, "jd_cache_backend", "redis")
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    text = "Requirements\n- Terraform required"
    _, _, first_hit = await analyse_jd_cached(text)
    assert first_hit is False
    _, _, second_hit = await analyse_jd_cached(text)
    assert second_hit is True
    reset_jd_cache()
