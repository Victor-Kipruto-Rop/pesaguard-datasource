"""Non-destructive worker preflight: validate DB schema and object-store access."""
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import inspect, select, func, text
from sqlalchemy.exc import SQLAlchemyError

from .database import engine, SessionLocal
from .config import settings
from .models import IngestionJob
from .storage import health_check

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("registry.preflight")

REQUIRED_TABLES = {
    "internal_organizations",
    "ingestion_jobs",
    "ingestion_row_errors",
    "ingestion_audit_logs",
    "organization_record_versions",
    "registry_sources",
    "warehouse_raw_imports",
    "warehouse_access_logs",
    "failed_imports_dlq",
    "api_keys",
    "api_key_audit_events",
}


def main() -> int:
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
            if engine.dialect.name == "postgresql":
                role = connection.execute(text("""
                    SELECT current_user AS role_name, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
                    FROM pg_roles WHERE rolname = current_user
                """)).mappings().first()
                if role and any(bool(role[field]) for field in ("rolsuper", "rolbypassrls", "rolcreaterole", "rolcreatedb")):
                    log.error("Database runtime role has elevated cluster privileges; use a least-privilege application role")
                    if settings.app_env.lower() == "production":
                        return 1
                    log.warning("Continuing outside production; reduce database role privileges before deployment")
                elif role:
                    log.info("Database role privilege check: least-privilege flags OK (role name withheld)")
        existing = set(inspect(engine).get_table_names())
        missing = sorted(REQUIRED_TABLES - existing)
        if missing:
            log.error("Database schema check failed; required tables are missing: %s", ", ".join(missing))
            return 1
        log.info("Database connectivity and required schema: OK")
        with SessionLocal() as db:
            queued = db.scalar(
                select(func.count()).select_from(IngestionJob).where(IngestionJob.status == "QUEUED")
            ) or 0
            processing = db.scalar(
                select(func.count()).select_from(IngestionJob).where(IngestionJob.status == "PROCESSING")
            ) or 0
            failed = db.scalar(
                select(func.count()).select_from(IngestionJob).where(IngestionJob.status == "FAILED")
            ) or 0
            oldest = db.scalar(
                select(func.min(IngestionJob.created_at)).where(IngestionJob.status == "QUEUED")
            )
        age_seconds = None
        if oldest is not None:
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            age_seconds = max(0, int((datetime.now(timezone.utc) - oldest).total_seconds()))
        log.info(
            "Queue summary: queued=%d processing=%d failed=%d oldest_queued_age_seconds=%s",
            queued, processing, failed, age_seconds if age_seconds is not None else "none",
        )
    except SQLAlchemyError:
        log.error("Database connectivity/schema check failed (details intentionally redacted)")
        return 1

    try:
        health_check()
        log.info("Private object storage connectivity: OK")
    except Exception:
        log.error("Private object storage connectivity: FAILED (details intentionally redacted)")
        return 1

    log.info("Preflight passed. No ingestion jobs were claimed or changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
