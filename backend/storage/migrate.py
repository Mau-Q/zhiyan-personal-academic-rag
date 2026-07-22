"""Apply the versioned PostgreSQL fact-source schema without exposing credentials."""

from __future__ import annotations

import argparse
import os
from hashlib import sha256

from backend.storage.postgres import Connection, MIGRATION_PATH, connect_postgres


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


def migration_bytes() -> bytes:
    return MIGRATION_PATH.read_bytes()


def migration_sha256() -> str:
    return sha256(migration_bytes()).hexdigest()


def apply_fact_source_migration(connection: Connection) -> bool:
    """Apply once and return True; return False when the same checksum is present."""

    checksum = migration_sha256()
    cursor = connection.cursor()
    try:
        cursor.execute(BOOTSTRAP_SQL)
        cursor.execute(
            """SELECT sha256 FROM rag_schema_migrations
               WHERE migration_id = %(migration_id)s""",
            {"migration_id": MIGRATION_ID},
        )
        existing = cursor.fetchone()
        if existing is not None:
            if existing["sha256"] != checksum:
                raise MigrationDriftError(
                    "applied PostgreSQL migration checksum differs from repository bytes"
                )
            connection.commit()
            return False
        cursor.execute(migration_bytes().decode("utf-8"))
        cursor.execute(
            """INSERT INTO rag_schema_migrations (migration_id, sha256)
               VALUES (%(migration_id)s, %(sha256)s)""",
            {"migration_id": MIGRATION_ID, "sha256": checksum},
        )
        connection.commit()
        return True
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
