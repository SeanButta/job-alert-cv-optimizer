"""
Background worker for polling job sources.

Periodically checks enabled sources and ingests new jobs.
Integrates with existing dedupe pipeline.
"""
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.sources import JobSource, SourceType, SourceStatus
from app.models.models import JobPost
from app.adapters.source_adapters import fetch_from_source, get_adapter, LinkedInRecruiterAdapter
from app.services.dedupe import compute_content_hash, compute_link_hash, is_duplicate_job

logger = logging.getLogger(__name__)

# Config
DEFAULT_POLL_INTERVAL = int(os.getenv('SOURCE_POLL_INTERVAL_SECONDS', '300'))  # 5 minutes
MIN_CHECK_INTERVAL = int(os.getenv('SOURCE_MIN_CHECK_INTERVAL_SECONDS', '60'))  # 1 minute
MAX_ERRORS_BEFORE_DISABLE = int(os.getenv('SOURCE_MAX_ERRORS', '5'))


def get_active_sources(db: Session, source_type: Optional[str] = None) -> list:
    """Get all active sources, optionally filtered by type."""
    query = select(JobSource).where(JobSource.status == SourceStatus.ACTIVE.value)
    
    if source_type:
        query = query.where(JobSource.type == source_type)
    
    return list(db.scalars(query).all())


def get_sources_due_for_check(
    db: Session,
    min_interval_seconds: int = MIN_CHECK_INTERVAL
) -> list:
    """Get active sources that are due for a check."""
    cutoff = datetime.utcnow() - timedelta(seconds=min_interval_seconds)
    
    # Active source types that should be polled
    # (linkedin_recruiter is passive - only used for tagging)
    active_source_types = [
        SourceType.TELEGRAM_CHANNEL.value,
        SourceType.TELEGRAM_PUBLIC.value,
        SourceType.WEBSITE.value,
    ]
    
    query = (
        select(JobSource)
        .where(
            JobSource.status == SourceStatus.ACTIVE.value,
            # Only poll active source types
            JobSource.type.in_(active_source_types),
            # Due for check: never checked or last check > interval ago
            (JobSource.last_checked == None) | (JobSource.last_checked < cutoff)
        )
        .order_by(JobSource.last_checked.asc().nullsfirst())
    )
    
    return list(db.scalars(query).all())


def get_linkedin_recruiters(db: Session) -> dict:
    """Get all active LinkedIn recruiters for job tagging."""
    sources = db.scalars(
        select(JobSource).where(
            JobSource.type == SourceType.LINKEDIN_RECRUITER.value,
            JobSource.status == SourceStatus.ACTIVE.value
        )
    ).all()
    
    recruiters = {}
    for source in sources:
        adapter = get_adapter(source)
        if isinstance(adapter, LinkedInRecruiterAdapter):
            info = adapter.get_recruiter_info()
            # Index by name and company for matching
            key = (info['recruiter_name'].lower(), info.get('company', '').lower())
            recruiters[key] = info
    
    return recruiters


def tag_job_with_recruiter(
    job_data: dict,
    recruiters: dict
) -> Optional[dict]:
    """
    Try to match job with a tracked recruiter.
    
    Matching heuristics:
    - Recruiter name appears in job description or company
    - Recruiter company matches job company
    
    Returns recruiter_info if matched, else None.
    """
    if not recruiters:
        return None
    
    description = (job_data.get('description') or '').lower()
    company = (job_data.get('company') or '').lower()
    title = (job_data.get('title') or '').lower()
    
    for (recruiter_name, recruiter_company), info in recruiters.items():
        # Check if recruiter name appears
        if recruiter_name and recruiter_name in description:
            return info
        
        # Check if recruiter company matches
        if recruiter_company and recruiter_company in company:
            return info
    
    return None


def ingest_job_from_source(
    db: Session,
    job_data: dict,
    recruiters: Optional[dict] = None
) -> Optional[JobPost]:
    """
    Ingest a single job post with dedupe.
    
    Returns JobPost if created, None if duplicate.
    """
    # Compute hashes for dedupe
    content_hash = compute_content_hash(
        job_data.get('title', ''),
        job_data.get('description', ''),
        job_data.get('company', '')
    )
    link_hash = compute_link_hash(job_data.get('link', ''))
    
    # Check for duplicates
    is_dup, dup_reason = is_duplicate_job(
        db, job_data['external_id'], content_hash, link_hash
    )
    if is_dup:
        logger.debug(f"Skipping duplicate job: {job_data['external_id']} ({dup_reason})")
        return None
    
    # Tag with recruiter if possible
    recruiter_info = None
    if recruiters:
        recruiter_info = tag_job_with_recruiter(job_data, recruiters)
    
    # Build description with recruiter tag if matched
    description = job_data.get('description', '')
    if recruiter_info:
        description = f"[Recruiter: {recruiter_info['recruiter_name']}] {description}"
    
    # Create job post
    job = JobPost(
        source=job_data.get('source', 'unknown'),
        external_id=job_data['external_id'],
        title=job_data.get('title', 'Untitled')[:255],
        company=job_data.get('company', '')[:255],
        description=description,
        link=job_data.get('link', ''),
        content_hash=content_hash,
        link_hash=link_hash,
    )
    db.add(job)
    db.flush()
    
    logger.info(f"Ingested job: {job.title} ({job.external_id})")
    return job


def poll_source(
    db: Session,
    source: JobSource,
    recruiters: Optional[dict] = None
) -> dict:
    """
    Poll a single source for new jobs.
    
    Returns:
        {
            'source_id': int,
            'jobs_found': int,
            'jobs_ingested': int,
            'error': str or None
        }
    """
    result = {
        'source_id': source.id,
        'source_type': source.type,
        'jobs_found': 0,
        'jobs_ingested': 0,
        'error': None,
    }
    
    try:
        # Fetch posts from source
        posts = fetch_from_source(source, limit=50)
        result['jobs_found'] = len(posts)
        
        # Ingest each post
        for post in posts:
            job = ingest_job_from_source(db, post, recruiters)
            if job:
                result['jobs_ingested'] += 1
        
        # Update source status on success
        source.last_checked = datetime.utcnow()
        source.last_error = None
        source.error_count = 0
        db.commit()
        
        logger.info(
            f"Polled source {source.id} ({source.type}): "
            f"{result['jobs_ingested']}/{result['jobs_found']} jobs ingested"
        )
    
    except Exception as e:
        result['error'] = str(e)
        
        # Update error state
        source.error_count += 1
        source.last_error = str(e)
        source.last_checked = datetime.utcnow()
        
        # Disable source after too many consecutive errors
        if source.error_count >= MAX_ERRORS_BEFORE_DISABLE:
            source.status = SourceStatus.ERROR.value
            logger.warning(
                f"Source {source.id} disabled after {source.error_count} errors"
            )
        
        db.commit()
        logger.error(f"Poll error for source {source.id}: {e}")
    
    return result


def run_poll_cycle(db: Session) -> dict:
    """
    Run a single poll cycle for all due sources.
    
    Returns summary of results.
    """
    # Get LinkedIn recruiters for tagging
    recruiters = get_linkedin_recruiters(db)
    
    # Get sources due for check
    sources = get_sources_due_for_check(db)
    
    if not sources:
        return {'sources_polled': 0, 'total_jobs_ingested': 0}
    
    results = []
    total_ingested = 0
    
    for source in sources:
        result = poll_source(db, source, recruiters)
        results.append(result)
        total_ingested += result['jobs_ingested']
    
    return {
        'sources_polled': len(sources),
        'total_jobs_ingested': total_ingested,
        'results': results,
    }


def run_source_poller(
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    max_iterations: int = 0,  # 0 = run forever
):
    """
    Main source poller loop.
    
    Args:
        poll_interval: Seconds between poll cycles
        max_iterations: Stop after N iterations (0 = forever)
    """
    logger.info(f"Source poller starting (interval={poll_interval}s)")
    
    iteration = 0
    while True:
        iteration += 1
        if max_iterations > 0 and iteration > max_iterations:
            logger.info(f"Reached max iterations ({max_iterations}), stopping")
            break
        
        db = SessionLocal()
        try:
            result = run_poll_cycle(db)
            
            if result['sources_polled'] > 0:
                logger.info(
                    f"Poll cycle complete: {result['sources_polled']} sources, "
                    f"{result['total_jobs_ingested']} jobs ingested"
                )
            else:
                logger.debug("No sources due for polling")
        
        except Exception as e:
            logger.error(f"Poll cycle error: {e}", exc_info=True)
        finally:
            db.close()
        
        time.sleep(poll_interval)
    
    logger.info("Source poller stopped")


def main():
    """CLI entry point."""
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Job source poller')
    parser.add_argument(
        '--poll-interval', type=float, default=DEFAULT_POLL_INTERVAL,
        help=f'Seconds between poll cycles (default: {DEFAULT_POLL_INTERVAL})'
    )
    parser.add_argument(
        '--max-iterations', type=int, default=0,
        help='Max iterations (0=forever, default: 0)'
    )
    args = parser.parse_args()
    
    run_source_poller(
        poll_interval=args.poll_interval,
        max_iterations=args.max_iterations,
    )


if __name__ == '__main__':
    main()
