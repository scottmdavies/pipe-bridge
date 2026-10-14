from pathlib import Path

from digital_workshop.config import Settings


def test_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("UPLOAD_DIR", "/tmp/x")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "5")
    monkeypatch.setenv("PROXIMITY_THRESHOLD", "1.5")
    monkeypatch.setenv("CONNECTION_TOLERANCE", "0.25")
    s = Settings.from_env()
    assert (
        s.database_url,
        s.upload_dir,
        s.max_upload_bytes,
        s.proximity_threshold,
        s.connection_tolerance,
    ) == (
        "sqlite://",
        Path("/tmp/x"),
        5,
        1.5,
        0.25,
    )


def test_defaults(monkeypatch) -> None:
    for name in (
        "DATABASE_URL",
        "UPLOAD_DIR",
        "MAX_UPLOAD_BYTES",
        "PROXIMITY_THRESHOLD",
        "CONNECTION_TOLERANCE",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.database_url.startswith("postgresql")
    assert settings.connection_tolerance == 1.0
