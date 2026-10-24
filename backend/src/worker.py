"""Run with: python -m src.worker [--batch]. PostgreSQL is required for multiple workers."""
import argparse
import logging
import random
import time
import traceback
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .cache import invalidate_lookup_keys
from .config import settings
from .database import SessionLocal
from .entity_resolution import similarity_score
from .ingestion.normalizer import normalize_record
from .ingestion.parser_csv import iter_csv_records_from_storage
from .models import (AuditLog, FailedImportDLQ, IngestionJob, IngestionRowError, Organization,
                     OrganizationRecordVersion, RegistrySource, WarehouseRawImport)
from .storage import delete_object, download_bytes

structlog.configure(processors=[structlog.processors.TimeStamper(fmt='iso'), structlog.processors.add_log_level,
                                structlog.processors.format_exc_info, structlog.processors.JSONRenderer()],
                    logger_factory=structlog.stdlib.LoggerFactory())
logging.basicConfig(level=logging.INFO, format='%(message)s')
log = structlog.get_logger('registry.worker')

DEFAULT_PRECEDENCE = 100
_SENSITIVE_KEY_PARTS = ('tax_pin', 'kra_pin', 'pin', 'phone', 'mobile', 'email', 'password', 'secret', 'token',
                        'account_number', 'identity_number', 'id_number')


class LeaseLost(Exception):
    """Another worker claimed this job after it was recovered as stale; stop writing."""


def _sanitize_dlq_row(row):
    safe = {}
    for key, value in row.items():
        normalized = str(key).strip().lower().replace('-', '_')
        safe[str(key)[:100]] = '[REDACTED]' if any(part in normalized for part in _SENSITIVE_KEY_PARTS) else (str(value)[:500] if value is not None else None)
    return safe


def _sanitize_diagnostic(value, row):
    text = str(value)
    for key, item in row.items():
        normalized = str(key).strip().lower().replace('-', '_')
        if item is not None and any(part in normalized for part in _SENSITIVE_KEY_PARTS):
            secret = str(item)
            if secret:
                text = text.replace(secret, '[REDACTED]')
    return text[:16000]


def now():
    return datetime.now(timezone.utc)


def _as_utc(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def snap(o):
    return {'legal_name': o.legal_name, 'normalized_legal_name': o.normalized_legal_name,
            'registration_number': o.registration_number, 'normalized_registration_number': o.normalized_registration_number,
            'tax_pin': o.tax_pin, 'normalized_tax_pin': o.normalized_tax_pin, 'status': o.status,
            'registry_payload': o.registry_payload or {}, 'data_quality_status': o.data_quality_status}


# ---------------------------------------------------------------- claiming and recovery
def claim_job():
    with SessionLocal() as db:
        stmt = (select(IngestionJob)
                .where(IngestionJob.status == 'QUEUED', (IngestionJob.next_attempt_at.is_(None)) | (IngestionJob.next_attempt_at <= now()))
                .order_by(IngestionJob.created_at).limit(1))
        if db.bind.dialect.name == 'postgresql':
            stmt = stmt.with_for_update(skip_locked=True)
        job = db.scalar(stmt)
        if not job:
            return None
        job.status = 'PROCESSING'
        job.attempts = (job.attempts or 0) + 1
        job.started_at = now()
        job.heartbeat_at = job.started_at
        job.next_attempt_at = None
        db.commit()
        return job.id


def recover_stale_jobs():
    """Requeue PROCESSING jobs whose heartbeat (or start time, for older rows) has gone quiet."""
    cutoff = now() - timedelta(seconds=max(60, settings.worker_stale_after_seconds))
    with SessionLocal() as db:
        last_signal = func.coalesce(IngestionJob.heartbeat_at, IngestionJob.started_at)
        stale = db.scalars(select(IngestionJob).where(IngestionJob.status == 'PROCESSING', last_signal < cutoff)).all()
        for job in stale:
            raw_import = db.scalar(select(WarehouseRawImport).where(WarehouseRawImport.ingestion_job_id == job.id))
            if job.attempts < settings.worker_max_attempts:
                job.status = 'QUEUED'
                job.next_attempt_at = now() + timedelta(seconds=max(1, settings.worker_retry_seconds))
                job.error_summary = 'Recovered stale processing job after worker interruption.'
                if raw_import:
                    raw_import.import_status = 'QUEUED'
            else:
                job.status = 'FAILED'
                job.completed_at = now()
                job.error_summary = 'Worker interrupted repeatedly; maximum attempts reached.'
                if raw_import:
                    raw_import.import_status = 'FAILED'
            db.add(AuditLog(action='registry_stale_job_recovered', actor='ingestion-worker', file_name=job.file_name,
                            details={'job_id': job.id, 'attempts': job.attempts, 'recovered_status': job.status}))
        if stale:
            db.commit()
            log.warning('stale_jobs_recovered', count=len(stale))


def expire_abandoned_uploads():
    """Fail direct-upload jobs that never completed and delete any partial object."""
    ttl = max(60, settings.direct_upload_url_ttl_seconds) + max(0, settings.upload_ttl_grace_seconds)
    cutoff = now() - timedelta(seconds=ttl)
    expired_keys = []
    with SessionLocal() as db:
        abandoned = db.scalars(select(IngestionJob).where(IngestionJob.status == 'UPLOADING', IngestionJob.created_at < cutoff)).all()
        for job in abandoned:
            raw_import = db.scalar(select(WarehouseRawImport).where(WarehouseRawImport.ingestion_job_id == job.id))
            job.status = 'FAILED'
            job.completed_at = now()
            job.error_summary = 'Direct upload was never completed and has expired.'
            if raw_import:
                raw_import.import_status = 'FAILED'
            if job.object_key:
                expired_keys.append(job.object_key)
            db.add(AuditLog(action='registry_abandoned_upload_expired', actor='ingestion-worker', file_name=job.file_name, details={'job_id': job.id}))
        if abandoned:
            db.commit()
    for key in expired_keys:
        delete_object(key)
    if expired_keys:
        log.warning('abandoned_uploads_expired', count=len(expired_keys))
    return len(expired_keys)


# ---------------------------------------------------------------- row processing
def _precedence(db, cache, source_key):
    """Lower number = more authoritative. Unregistered sources get the default."""
    if source_key not in cache:
        value = db.scalar(select(RegistrySource.precedence).where(RegistrySource.source_key == source_key))
        cache[source_key] = DEFAULT_PRECEDENCE if value is None else value
    return cache[source_key]


def _escape_like(text):
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _duplicate_candidates(db, cache, rec):
    """Fuzzy-match a new name against organizations sharing its first three characters."""
    tokens = (rec.get('normalized_legal_name') or '').split()
    prefix = tokens[0][:3] if tokens else ''
    if not prefix or not rec.get('legal_name'):
        return [], prefix
    if prefix not in cache:
        cache[prefix] = list(db.execute(
            select(Organization.id, Organization.legal_name)
            .where(Organization.normalized_legal_name.ilike(_escape_like(prefix) + '%', escape='\\'))
            .order_by(Organization.normalized_legal_name).limit(max(1, settings.entity_resolution_max_candidates))).all())
    found = []
    for candidate_id, candidate_name in cache[prefix]:
        score = similarity_score(rec['legal_name'], candidate_name)
        if score >= 92.0:
            found.append({'organization_id': candidate_id, 'similarity_score': score})
    return found, prefix


def _find_existing(db, rec):
    reg, pin = rec.get('normalized_registration_number'), rec.get('normalized_tax_pin')
    if reg:
        return db.scalar(select(Organization).where(Organization.normalized_registration_number == reg).limit(1))
    if pin:
        return db.scalar(select(Organization).where(Organization.normalized_tax_pin == pin).limit(1))
    return None


def _upsert_row(db, job, rec, row_num, ctx):
    """Apply one normalized record. Returns inserted | updated | unchanged | precedence_skipped."""
    source_key = job.source_name or 'uploaded_dataset'
    reg, pin = rec.get('normalized_registration_number'), rec.get('normalized_tax_pin')
    existing = _find_existing(db, rec)
    if existing is not None:
        if existing.source_name and existing.source_name != source_key and \
                _precedence(db, ctx['precedence'], existing.source_name) < _precedence(db, ctx['precedence'], source_key):
            db.add(AuditLog(action='registry_lower_precedence_update_skipped', actor='ingestion-worker', file_name=job.file_name,
                            details={'job_id': job.id, 'row_number': row_num, 'organization_id': existing.id,
                                     'existing_source': existing.source_name, 'incoming_source': source_key}))
            return 'precedence_skipped'
        if not any(getattr(existing, key) != value for key, value in rec.items()):
            existing.last_seen_at = now()  # same content: refresh freshness only, no new version
            return 'unchanged'
        before = snap(existing)
        for key in (existing.normalized_registration_number and f'registry:lookup:reg:{existing.normalized_registration_number}',
                    existing.normalized_tax_pin and f'registry:lookup:pin:{existing.normalized_tax_pin}'):
            if key:
                ctx['changed_keys'].add(key)
        for key, value in rec.items():
            setattr(existing, key, value)
        existing.source_file, existing.source_row, existing.source_name = job.file_name, row_num, source_key
        existing.source_record_id = reg or pin
        existing.last_seen_at = now()
        if existing.data_quality_status != 'POSSIBLE_DUPLICATE_REVIEW':
            existing.data_quality_status = 'IMPORTED_UNVERIFIED'  # changed content invalidates earlier review
        db.flush()
        db.add(OrganizationRecordVersion(organization_id=existing.id, change_type='UPDATED', snapshot={'before': before, 'after': snap(existing)},
                                         source_name=source_key, source_file=job.file_name, source_row=row_num))
        return 'updated'
    duplicates, prefix = _duplicate_candidates(db, ctx['dup_cache'], rec)
    quality = 'POSSIBLE_DUPLICATE_REVIEW' if duplicates else 'IMPORTED_UNVERIFIED'
    org = Organization(**rec, source_file=job.file_name, source_row=row_num, source_name=source_key,
                       source_record_id=reg or pin, last_seen_at=now(), data_quality_status=quality)
    db.add(org)
    db.flush()
    if prefix in ctx['dup_cache']:
        ctx['dup_cache'][prefix].append((org.id, org.legal_name))
    db.add(OrganizationRecordVersion(organization_id=org.id, change_type='CREATED_POSSIBLE_DUPLICATE' if duplicates else 'CREATED',
                                     snapshot={'after': snap(org), 'possible_duplicate_candidates': duplicates},
                                     source_name=source_key, source_file=job.file_name, source_row=row_num))
    if duplicates:
        db.add(AuditLog(action='registry_possible_duplicate_candidate', actor='ingestion-worker', file_name=job.file_name,
                        details={'job_id': job.id, 'row_number': row_num, 'new_organization_id': org.id, 'candidates': duplicates,
                                 'decision': 'manual_review_required'}))
    return 'inserted'


def _record_row_failure(db, job, row_num, row, exc, code, message=None):
    text = _sanitize_diagnostic(message or exc, row)[:1000]
    db.add(IngestionRowError(job_id=job.id, row_number=row_num, error_code=code, message=text))
    db.add(FailedImportDLQ(job_id=job.id, row_number=row_num, error_code=code, error_type=type(exc).__name__, message=text,
                           sanitized_row=_sanitize_dlq_row(row), traceback_text=_sanitize_diagnostic(traceback.format_exc(), row)))


def _row_savepoint(db):
    # Row-level isolation of database errors needs SAVEPOINT support (PostgreSQL).
    return db.begin_nested() if (settings.ingestion_row_savepoints and db.bind.dialect.name == 'postgresql') else nullcontext()


# ---------------------------------------------------------------- job processing
def _process_pdf(db, job, raw_import):
    from .ingestion.pdf_text import MAX_PDF_BYTES, extract_pdf_text
    if raw_import and raw_import.byte_size > MAX_PDF_BYTES:
        job.status = 'NEEDS_PDF_PROCESSING'
        job.error_summary = 'PDF retained in private storage; automatic diagnostics are limited to 50 MiB. Manual review is required.'
        job.completed_at = now()
        raw_import.import_status = 'NEEDS_PDF_PROCESSING'
        db.add(AuditLog(action='registry_pdf_size_limit_manual_review', actor='ingestion-worker', file_name=job.file_name,
                        details={'job_id': job.id, 'byte_size': raw_import.byte_size, 'manual_review_required': True}))
        db.commit()
        return
    data = download_bytes(job.object_key)
    diagnostics = extract_pdf_text(data, enable_ocr=settings.pdf_ocr_enabled, max_ocr_pages=settings.pdf_ocr_max_pages)
    job.status = 'NEEDS_PDF_PROCESSING'
    if diagnostics.needs_ocr and diagnostics.extracted_characters:
        job.error_summary = f'Extracted {diagnostics.extracted_characters} character(s) from {diagnostics.page_count} page(s), but OCR coverage is incomplete; manual review is required.'
    elif diagnostics.needs_ocr and diagnostics.ocr_attempted and not diagnostics.ocr_available:
        job.error_summary = f'PDF has {diagnostics.page_count} page(s); OCR was unavailable or failed, so manual review is required.'
    elif diagnostics.needs_ocr:
        job.error_summary = f'PDF has {diagnostics.page_count} page(s) but no searchable text; OCR and manual review are required.'
    else:
        job.error_summary = f'Extracted {diagnostics.extracted_characters} character(s) from {diagnostics.page_count} page(s); manual review is required. Extracted text is not treated as verified data.'
    if raw_import:
        raw_import.import_status = 'NEEDS_PDF_PROCESSING'
        metadata = dict(raw_import.metadata_json or {})
        metadata.update({'pdf_page_count': diagnostics.page_count, 'pdf_extracted_characters': diagnostics.extracted_characters,
                         'pdf_needs_ocr': diagnostics.needs_ocr, 'pdf_extraction_version': 2, 'pdf_ocr_attempted': diagnostics.ocr_attempted,
                         'pdf_ocr_available': diagnostics.ocr_available, 'pdf_ocr_pages_processed': diagnostics.ocr_pages_processed,
                         'requires_manual_review': True})
        raw_import.metadata_json = metadata
    job.completed_at = now()
    db.add(AuditLog(action='registry_pdf_extraction_diagnostics', actor='ingestion-worker', file_name=job.file_name,
                    details={'job_id': job.id, 'page_count': diagnostics.page_count, 'extracted_characters': diagnostics.extracted_characters,
                             'needs_ocr': diagnostics.needs_ocr, 'ocr_attempted': diagnostics.ocr_attempted,
                             'ocr_available': diagnostics.ocr_available, 'ocr_pages_processed': diagnostics.ocr_pages_processed,
                             'manual_review_required': True}))
    db.commit()


def _process_csv(db, job, raw_import):
    job_id = job.id
    lease_attempts = job.attempts
    if raw_import:
        raw_import.import_status = 'PROCESSING'
        db.flush()
    counts = {'processed': job.records_processed or 0, 'inserted': job.records_inserted or 0, 'updated': job.records_updated or 0,
              'skipped': job.records_skipped or 0}
    unchanged = precedence_skipped = 0
    ctx = {'changed_keys': set(), 'dup_cache': {}, 'precedence': {}}
    batch_count = 0
    last_commit = time.monotonic()
    last_row_number = job.last_processed_row or 1

    for row_num, row in iter_csv_records_from_storage(job.object_key, settings.max_records_per_file):
        if row_num <= last_row_number:
            continue
        counts['processed'] += 1
        batch_count += 1
        last_row_number = row_num
        try:
            with _row_savepoint(db):
                rec = normalize_record(row)
                if rec.get('normalized_registration_number'):
                    ctx['changed_keys'].add(f"registry:lookup:reg:{rec['normalized_registration_number']}")
                if rec.get('normalized_tax_pin'):
                    ctx['changed_keys'].add(f"registry:lookup:pin:{rec['normalized_tax_pin']}")
                outcome = _upsert_row(db, job, rec, row_num, ctx)
            if outcome in ('inserted', 'updated'):
                counts[outcome] += 1
            elif outcome == 'unchanged':
                unchanged += 1
            else:
                precedence_skipped += 1
        except ValueError as exc:
            counts['skipped'] += 1
            _record_row_failure(db, job, row_num, row, exc, 'INVALID_ROW')
        except IntegrityError as exc:
            if not (settings.ingestion_row_savepoints and db.bind.dialect.name == 'postgresql'):
                raise
            counts['skipped'] += 1
            _record_row_failure(db, job, row_num, row, exc, 'DB_CONSTRAINT', 'Row conflicts with an existing record (duplicate identifier).')
        due = batch_count >= max(1, settings.ingestion_batch_size) or \
            (batch_count and time.monotonic() - last_commit >= max(1, settings.worker_commit_interval_seconds))
        if due:
            job.last_processed_row = last_row_number
            job.records_processed, job.records_inserted = counts['processed'], counts['inserted']
            job.records_updated, job.records_skipped = counts['updated'], counts['skipped']
            job.heartbeat_at = now()
            if raw_import:
                raw_import.import_status = 'PROCESSING'
            db.commit()
            invalidate_lookup_keys(ctx['changed_keys'])
            ctx['changed_keys'].clear()
            ctx['dup_cache'].clear()
            db.expunge_all()
            job = db.get(IngestionJob, job_id)
            if job is None or job.attempts != lease_attempts:
                raise LeaseLost(job_id)
            raw_import = db.scalar(select(WarehouseRawImport).where(WarehouseRawImport.ingestion_job_id == job.id))
            batch_count = 0
            last_commit = time.monotonic()

    job.last_processed_row = last_row_number
    job.records_processed, job.records_inserted = counts['processed'], counts['inserted']
    job.records_updated, job.records_skipped = counts['updated'], counts['skipped']
    job.status = 'COMPLETED_WITH_ERRORS' if counts['skipped'] else 'COMPLETED'
    if raw_import:
        raw_import.import_status = job.status
    job.error_summary = f"{counts['skipped']} row(s) were skipped; see row-errors endpoint." if counts['skipped'] else None
    job.completed_at = now()
    job.heartbeat_at = job.completed_at
    db.add(AuditLog(action='registry_ingestion_completed', actor='ingestion-worker', file_name=job.file_name,
                    details={'job_id': job.id, 'processed': counts['processed'], 'inserted': counts['inserted'], 'updated': counts['updated'],
                             'skipped': counts['skipped'], 'unchanged': unchanged, 'precedence_skipped': precedence_skipped}))
    db.commit()
    invalidate_lookup_keys(ctx['changed_keys'])
    log.info('ingestion_job_completed', job_id=job_id, request_id=job.correlation_id, status=job.status, unchanged=unchanged,
             precedence_skipped=precedence_skipped, **counts)


def _retry_delay_seconds(attempts: int) -> int:
    """Return bounded exponential backoff with jitter to avoid synchronized retry storms."""
    base = max(1, int(settings.worker_retry_seconds))
    ceiling = max(base, int(settings.worker_retry_max_seconds))
    exponent = min(max(0, int(attempts) - 1), 30)
    exponential = min(ceiling, base * (2 ** exponent))
    # Equal jitter: retain at least half the delay while spreading concurrent retries.
    return max(1, int(round(random.uniform(exponential * 0.5, exponential))))


def _schedule_retry_or_fail(job_id, exc):
    with SessionLocal() as retry_db:
        job = retry_db.get(IngestionJob, job_id)
        if not job:
            return
        raw_import = retry_db.scalar(select(WarehouseRawImport).where(WarehouseRawImport.ingestion_job_id == job.id))
        if job.attempts < settings.worker_max_attempts:
            job.status = 'QUEUED'
            if raw_import:
                raw_import.import_status = 'QUEUED'
            job.next_attempt_at = now() + timedelta(seconds=_retry_delay_seconds(job.attempts))
            job.error_summary = f'Attempt {job.attempts} failed; retry scheduled. {str(exc)[:500]}'
        else:
            job.status = 'FAILED'
            if raw_import:
                raw_import.import_status = 'FAILED'
            job.error_summary = f'Ingestion failed after {job.attempts} attempts: {str(exc)[:800]}'
            job.completed_at = now()
        retry_db.commit()


def process_job(job_id):
    with SessionLocal() as db:
        job = db.get(IngestionJob, job_id)
        if not job:
            return
        log.info('ingestion_job_started', job_id=job_id, request_id=job.correlation_id)
        try:
            if not job.object_key:
                raise RuntimeError('Ingestion source object is missing')
            raw_import = db.scalar(select(WarehouseRawImport).where(WarehouseRawImport.ingestion_job_id == job.id))
            if '.' in job.file_name and job.file_name.rsplit('.', 1)[-1].lower() == 'pdf':
                _process_pdf(db, job, raw_import)
            else:
                _process_csv(db, job, raw_import)
        except LeaseLost:
            db.rollback()
            log.warning('ingestion_lease_lost', job_id=job_id)
        except Exception as exc:
            db.rollback()
            _schedule_retry_or_fail(job_id, exc)
            log.error('job_processing_failed', job_id=job_id, error_type=type(exc).__name__)


def run_batch(max_jobs=None):
    """Process a bounded number of eligible jobs, then exit for scheduled runners."""
    limit = max(1, int(max_jobs if max_jobs is not None else settings.worker_max_jobs_per_run))
    log.info('scheduled_ingestion_batch_starting', max_jobs=limit)
    recover_stale_jobs()
    expire_abandoned_uploads()
    processed = 0
    for _ in range(limit):
        job_id = claim_job()
        if not job_id:
            break
        process_job(job_id)
        processed += 1
    log.info('scheduled_ingestion_batch_finished', claimed_jobs=processed)
    return processed


def run_forever():
    log.info('ingestion_worker_starting')
    while True:
        try:
            recover_stale_jobs()
            expire_abandoned_uploads()
            job_id = claim_job()
            if job_id:
                process_job(job_id)
            else:
                time.sleep(max(0.25, settings.worker_poll_seconds))
        except KeyboardInterrupt:
            break
        except Exception as exc:
            log.error('worker_loop_error', error_type=type(exc).__name__)
            time.sleep(max(1, settings.worker_retry_seconds))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PesaGuard ingestion worker')
    parser.add_argument('--batch', action='store_true', help='Process a bounded batch and exit')
    parser.add_argument('--max-jobs', type=int, default=None, help='Override the batch job limit')
    args = parser.parse_args()
    if args.batch:
        run_batch(args.max_jobs)
    else:
        run_forever()
