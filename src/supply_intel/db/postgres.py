from __future__ import annotations

import hashlib
import ssl
from pathlib import Path
from typing import Any, Protocol, cast

import asyncpg  # type: ignore[import-untyped]

from supply_intel.models.base import StrictBaseModel
from supply_intel.settings import Settings


def migration_files(root: Path = Path("migrations")) -> list[Path]:
    return sorted(root.glob("*.sql"))


def load_migration_text(root: Path = Path("migrations")) -> str:
    return "\n\n".join(path.read_text(encoding="utf-8") for path in migration_files(root))


class PostgresConnection(Protocol):
    async def execute(self, query: str, *args: object) -> str: ...

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]: ...

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None: ...

    async def close(self) -> None: ...


class PostgresMigrationResult(StrictBaseModel):
    version: str
    path: str
    checksum: str
    status: str


SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version text PRIMARY KEY,
  checksum text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
"""


def postgres_ssl_context(ca_cert_path: Path | None = None) -> ssl.SSLContext | None:
    if ca_cert_path is None:
        return None
    return ssl.create_default_context(cafile=str(ca_cert_path))


async def connect_database(
    database_url: str,
    *,
    ca_cert_path: Path | None = None,
) -> PostgresConnection:
    context = postgres_ssl_context(ca_cert_path)
    if context is None:
        return cast(PostgresConnection, await asyncpg.connect(database_url))
    return cast(PostgresConnection, await asyncpg.connect(database_url, ssl=context))


async def connect_postgres(settings: Settings) -> PostgresConnection:
    return await connect_database(
        settings.database_url,
        ca_cert_path=settings.database_ca_cert_path,
    )


def migration_version(path: Path) -> str:
    return path.stem


def migration_checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


async def apply_migrations(
    database_url: str,
    root: Path = Path("migrations"),
    connection: PostgresConnection | None = None,
    ca_cert_path: Path | None = None,
) -> list[PostgresMigrationResult]:
    if connection is not None:
        return await apply_migrations_with_connection(connection, root)

    raw_connection = await connect_database(database_url, ca_cert_path=ca_cert_path)
    try:
        return await apply_migrations_with_connection(raw_connection, root)
    finally:
        await raw_connection.close()


async def apply_migrations_with_connection(
    connection: PostgresConnection,
    root: Path = Path("migrations"),
) -> list[PostgresMigrationResult]:
    await connection.execute(SCHEMA_MIGRATIONS_SQL)
    results: list[PostgresMigrationResult] = []
    for path in migration_files(root):
        sql = path.read_text(encoding="utf-8")
        version = migration_version(path)
        checksum = migration_checksum(sql)
        existing = await connection.fetchrow(
            "SELECT checksum FROM schema_migrations WHERE version = $1",
            version,
        )
        if existing is not None:
            existing_checksum = str(existing["checksum"])
            if existing_checksum != checksum:
                raise ValueError(
                    f"Migration {version} checksum changed: {existing_checksum} != {checksum}"
                )
            results.append(
                PostgresMigrationResult(
                    version=version,
                    path=str(path),
                    checksum=checksum,
                    status="skipped",
                )
            )
            continue

        await connection.execute(sql)
        await connection.execute(
            "INSERT INTO schema_migrations (version, checksum) VALUES ($1, $2)",
            version,
            checksum,
        )
        results.append(
            PostgresMigrationResult(
                version=version,
                path=str(path),
                checksum=checksum,
                status="applied",
            )
        )
    return results
