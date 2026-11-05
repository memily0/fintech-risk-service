"""Fail-closed configuration for local fixture development only."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / ".arcshift-v1/fixtures.sqlite3"


@dataclass(frozen=True)
class Settings:
    environment: str = "local"
    data_mode: str = "synthetic"
    host: str = "127.0.0.1"
    port: int = 8765
    storage_backend: str = "sqlite"
    database_path: Path = DEFAULT_DATABASE_PATH

    def __post_init__(self):
        if self.environment not in {"local", "test"}:
            raise ValueError("Only local/test environments are implemented")
        if self.data_mode != "synthetic":
            raise ValueError("Only synthetic fixture mode is implemented")
        if self.host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Fixture backend must bind to IPv4 loopback")
        if type(self.port) is not int or not 1024 <= self.port <= 65535:
            raise ValueError("Port must be an integer between 1024 and 65535")
        if self.storage_backend not in {"sqlite", "memory"}:
            raise ValueError("Only local SQLite or memory fixture stores are implemented")
        if not str(self.database_path).strip() or str(self.database_path) == ":memory:":
            raise ValueError("Use a file path for SQLite or select memory storage explicitly")
        path = Path(self.database_path).expanduser()
        object.__setattr__(self, "database_path", (PROJECT_ROOT / path).resolve())

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None):
        env = os.environ if values is None else values
        try:
            port = int(env.get("ARCSHIFT_PORT", "8765"))
        except ValueError as exc:
            raise ValueError("ARCSHIFT_PORT must be an integer") from exc
        return cls(
            environment=env.get("ARCSHIFT_ENVIRONMENT", "local"),
            data_mode=env.get("ARCSHIFT_DATA_MODE", "synthetic"),
            host=env.get("ARCSHIFT_HOST", "127.0.0.1"),
            port=port,
            storage_backend=env.get("ARCSHIFT_STORAGE_BACKEND", "sqlite"),
            database_path=env.get("ARCSHIFT_DB_PATH", str(DEFAULT_DATABASE_PATH)),
        )
