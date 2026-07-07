"""Copy the local SQLite Newser database into an empty Supabase Postgres DB."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import Base, normalize_database_url  # noqa: E402

APP_TABLES = ["clusters", "dynamic_keywords", "macro_resumenes", "noticias", "tendencias"]
INTEGER_PK_TABLES = ["clusters", "macro_resumenes", "tendencias"]


def _engine(database_url: str) -> Engine:
    kwargs: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(database_url, **kwargs)


def _row_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            table_name: conn.execute(select(func.count()).select_from(Base.metadata.tables[table_name])).scalar_one()
            for table_name in APP_TABLES
        }


def _primary_keys(engine: Engine, table_name: str) -> set[tuple[Any, ...]]:
    table = Base.metadata.tables[table_name]
    pk_columns = list(table.primary_key.columns)
    with engine.connect() as conn:
        return {tuple(row) for row in conn.execute(select(*pk_columns))}


def _cluster_orphans(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT COUNT(*) "
                "FROM noticias n "
                "LEFT JOIN clusters c ON n.cluster_id = c.id "
                "WHERE n.cluster_id IS NOT NULL AND c.id IS NULL"
            )
        ).scalar_one()


def _copy_table(source: Engine, target: Engine, table_name: str) -> int:
    table = Base.metadata.tables[table_name]
    with source.connect() as source_conn:
        rows = [dict(row) for row in source_conn.execute(select(table)).mappings()]
    if not rows:
        return 0
    with target.begin() as target_conn:
        target_conn.execute(table.insert(), rows)
    return len(rows)


def _reset_sequences(target: Engine) -> None:
    with target.begin() as conn:
        for table_name in INTEGER_PK_TABLES:
            sequence = conn.execute(
                text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                {"table_name": table_name},
            ).scalar_one()
            if sequence:
                conn.execute(
                    text(
                        "SELECT setval("
                        "CAST(:sequence AS regclass), "
                        f"COALESCE((SELECT MAX(id) FROM {table_name}), 1), "
                        f"(SELECT COUNT(*) > 0 FROM {table_name})"
                        ")"
                    ),
                    {"sequence": sequence},
                )


def _verify(source: Engine, target: Engine) -> None:
    source_counts = _row_counts(source)
    target_counts = _row_counts(target)
    if source_counts != target_counts:
        raise RuntimeError(f"Row count mismatch: source={source_counts}, target={target_counts}")

    for table_name in APP_TABLES:
        if _primary_keys(source, table_name) != _primary_keys(target, table_name):
            raise RuntimeError(f"Primary key mismatch in {table_name}")

    source_orphans = _cluster_orphans(source)
    target_orphans = _cluster_orphans(target)
    if source_orphans != target_orphans:
        raise RuntimeError(f"cluster_id orphan mismatch: source={source_orphans}, target={target_orphans}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default="sqlite:///news_analyzer.db")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    target_url = normalize_database_url(os.getenv("DATABASE_URL", "").strip())
    if not target_url or target_url.startswith("sqlite"):
        raise SystemExit("Set DATABASE_URL to your Supabase Postgres connection string before running this script.")

    source = _engine(args.source_url)
    target = _engine(target_url)

    Base.metadata.create_all(bind=target)
    source_counts = _row_counts(source)
    target_counts = _row_counts(target)

    print("Source row counts:", source_counts)
    print("Target row counts before copy:", target_counts)
    if any(target_counts.values()):
        raise SystemExit("Refusing to copy into a non-empty target. Use a fresh Supabase database for this migration.")

    for table_name in APP_TABLES:
        copied = _copy_table(source, target, table_name)
        print(f"Copied {copied} row(s) into {table_name}.")

    _reset_sequences(target)
    _verify(source, target)

    print("Target row counts after copy:", _row_counts(target))
    print("cluster_id orphan count:", _cluster_orphans(target))
    print("Migration verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
