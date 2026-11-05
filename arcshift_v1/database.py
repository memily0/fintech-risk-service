"""Versioned local SQLite migrations; never opens a production database."""

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


APPLICATION_ID = 0x41535631
MIGRATIONS = Path(__file__).resolve().parent / "migrations"


class SchemaError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


def load_migrations(directory: Path = MIGRATIONS) -> tuple[Migration, ...]:
    migrations = []
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        raw = path.read_bytes()
        migrations.append(Migration(int(path.name.split("_", 1)[0]), path.name, raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()))
    if not migrations or [m.version for m in migrations] != list(range(1, len(migrations) + 1)):
        raise SchemaError("Migration files must form a contiguous sequence starting at 1")
    return tuple(migrations)


def connect(path: Path, *, readonly: bool = False, create: bool = True):
    mode = "ro" if readonly else ("rwc" if create else "rw")
    uri = path.resolve().as_uri() + "?mode=" + mode
    connection = sqlite3.connect(uri, uri=True, timeout=2, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if readonly:
        connection.execute("PRAGMA query_only = ON")
    return connection


def _validate_ledger(connection, migrations, *, allow_empty=False):
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    app_id = connection.execute("PRAGMA application_id").fetchone()[0]
    user_version = connection.execute("PRAGMA user_version").fetchone()[0]
    if not tables:
        if allow_empty and app_id == 0 and user_version == 0:
            return 0
        raise SchemaError("Missing fixture schema")
    if app_id != APPLICATION_ID or "schema_migrations" not in tables:
        raise SchemaError("Refusing to modify a database not owned by this fixture application")
    rows = connection.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version").fetchall()
    versions = [row["version"] for row in rows]
    if versions != list(range(1, len(rows) + 1)) or len(rows) > len(migrations):
        raise SchemaError("Unknown or non-contiguous database schema version")
    for row, migration in zip(rows, migrations):
        if row["name"] != migration.name or row["checksum"] != migration.checksum:
            raise SchemaError("An applied migration was modified")
    if user_version != len(rows):
        raise SchemaError("Database schema version and migration ledger disagree")
    return len(rows)


def _execute_migration(connection, sql):
    # executescript may commit implicitly; use complete_statement within our transaction.
    statement = ""
    for line in sql.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""
    if statement.strip():
        raise SchemaError("Migration has an incomplete SQL statement")


def migrate(path: Path, directory: Path = MIGRATIONS) -> int:
    migrations = load_migrations(directory)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with closing(connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            applied = _validate_ledger(connection, migrations, allow_empty=True)
            if applied == 0:
                connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)")
                connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            for migration in migrations[applied:]:
                _execute_migration(connection, migration.sql)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                    (migration.version, migration.name, migration.checksum, datetime.now(timezone.utc).isoformat()),
                )
                connection.execute(f"PRAGMA user_version = {migration.version}")
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
    path.chmod(0o600)
    return len(migrations)


def check_schema(path: Path, directory: Path = MIGRATIONS) -> int:
    migrations = load_migrations(directory)
    with closing(connect(path, readonly=True)) as connection:
        version = _validate_ledger(connection, migrations)
        if version != len(migrations):
            raise SchemaError("Database needs pending migrations")
        return version


def main():
    from .settings import Settings

    parser = argparse.ArgumentParser(description="Local synthetic SQLite schema only; no model or source operations")
    parser.add_argument("--check", action="store_true", help="Read-only schema check; never creates a database")
    args = parser.parse_args()
    settings = Settings.from_env()
    if settings.storage_backend != "sqlite":
        parser.error("Select sqlite storage to use this migration command")
    version = check_schema(settings.database_path) if args.check else migrate(settings.database_path)
    print(json.dumps({"schema_version": version, "data_mode": "synthetic", "production_ready": False}))


if __name__ == "__main__":
    main()
