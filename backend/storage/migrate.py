"""Apply the versioned PostgreSQL fact-source schema without exposing credentials."""

from __future__ import annotations

import argparse
import os
from hashlib import sha256

from backend.storage.postgres import Connection, MIGRATION_PATHS, connect_postgres


MIGRATION_ID = "0001_fact_source"
BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS rag_schema_migrations (
    migration_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


class MigrationDriftError(RuntimeError):
    """Raised when an applied migration no longer matches repository bytes."""


def migration_bytes(migration_id: str = MIGRATION_ID) -> bytes:
    try:
        path = MIGRATION_PATHS[migration_id]
    except KeyError as exc:
        raise ValueError(f"unknown PostgreSQL migration: {migration_id}") from exc
    return path.read_bytes()


def migration_sha256(migration_id: str = MIGRATION_ID) -> str:
    return sha256(migration_bytes(migration_id)).hexdigest()


def apply_fact_source_migration(connection: Connection) -> bool:
    """Apply once and return True; return False when the same checksum is present."""

    cursor = connection.cursor()
    try:
        cursor.execute(BOOTSTRAP_SQL)
        applied = False
        for migration_id in MIGRATION_PATHS:
            checksum = migration_sha256(migration_id)
            cursor.execute(
                """SELECT sha256 FROM rag_schema_migrations
                   WHERE migration_id = %(migration_id)s""",
                {"migration_id": migration_id},
            )
            existing = cursor.fetchone()
            if existing is not None:
                if existing["sha256"] != checksum:
                    raise MigrationDriftError(
                        "applied PostgreSQL migration checksum differs from repository bytes"
                    )
                continue
            cursor.execute(migration_bytes(migration_id).decode("utf-8"))
            cursor.execute(
                """INSERT INTO rag_schema_migrations (migration_id, sha256)
                   VALUES (%(migration_id)s, %(sha256)s)""",
                {"migration_id": migration_id, "sha256": checksum},
            )
            applied = True
        connection.commit()
        return applied
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url-env",
        default="DATABASE_URL",
        help="environment variable containing the PostgreSQL DSN",
    )
    args = parser.parse_args()
    database_url = os.getenv(args.database_url_env)
    if not database_url:
        parser.error(f"environment variable {args.database_url_env} is empty")
    connection = connect_postgres(database_url)
    applied = apply_fact_source_migration(connection)
    print(f"PostgreSQL fact-source migration: {'APPLIED' if applied else 'UNCHANGED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
