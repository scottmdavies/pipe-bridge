from pathlib import Path

from digital_workshop.config import Settings


def test_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("UPLOAD_DIR", "/tmp/x")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "5")
    monkeypatch.setenv("PROXIMITY_THRESHOLD", "1.5")
    s = Settings.from_env()
    assert (s.database_url, s.upload_dir, s.max_upload_bytes, s.proximity_threshold) == (
        "sqlite://",
        Path("/tmp/x"),
        5,
        1.5,
    )


def test_defaults(monkeypatch) -> None:
    for name in ("DATABASE_URL", "UPLOAD_DIR", "MAX_UPLOAD_BYTES", "PROXIMITY_THRESHOLD"):
        monkeypatch.delenv(name, raising=False)
    assert Settings.from_env().database_url.startswith("postgresql")
