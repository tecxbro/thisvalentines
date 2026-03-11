import pytest

from reels_backend.config import _required_env_any


def test_required_env_any_returns_first_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELEVEN_API_KEY", raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fallback-key")

    assert _required_env_any("ELEVEN_API_KEY", "ELEVENLABS_API_KEY") == "fallback-key"


def test_required_env_any_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELEVEN_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Missing required environment variable"):
        _required_env_any("ELEVEN_API_KEY", "ELEVENLABS_API_KEY")
