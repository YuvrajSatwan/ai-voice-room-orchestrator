import pytest

from roxstar.config import ConfigurationError, Settings


def test_settings_rejects_missing_livekit_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("roxstar.config.load_dotenv", lambda: None)
    for variable in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(ConfigurationError, match="LIVEKIT_URL"):
        Settings.from_environment()


def test_settings_allows_local_non_livekit_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROXSTAR_LOG_FORMAT", "text")
    settings = Settings.from_environment(require_livekit=False)
    assert settings.log_format == "text"
