"""
Queue worker for processing notification tasks.

Run with: python -m app.services.worker
Or via CLI: python scripts/run_worker.py
"""
import os
import sys
import time
import logging
from datetime import datetime
from typing import Callable, Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('notification_worker')


def process_single_task(task, send_fn: Callable[[str, str, str], Dict[str, Any]]) -> tuple[bool, str]:
    """
    Process a single notification task.
    Returns (success, error_message).
    """
    try:
        result = send_fn(task.channel, task.target, task.message)
        status = result.get('status', '')
        if status in ('sent', 'mock_sent'):
            return True, ''
        else:
            error = result.get('error', f"Status: {status}")
            return False, error
    except Exception as e:
        return False, str(e)


def run_worker(
    poll_interval: float = 5.0,
    batch_size: int = 10,
    max_iterations: int = 0,  # 0 = run forever
    send_fn: Callable[[str, str, str], Dict[str, Any]] = None,
):
    """
    Main worker loop.

    Args:
        poll_interval: Seconds between queue polls
        batch_size: Max tasks to fetch per iteration
        max_iterations: Stop after N iterations (0 = forever)
        send_fn: Function(channel, target, message) -> dict with 'status' key
    """
    from app.db.database import SessionLocal
    from app.services.queue import (
        fetch_pending_tasks,
        mark_task_processing,
        mark_task_completed,
        mark_task_failed,
    )
    from app.services.notifier import (
        send_email, send_sms, send_telegram, send_whatsapp
    )

    # Default send function
    if send_fn is None:
        def default_send(channel: str, target: str, message: str) -> Dict[str, Any]:
            dispatchers = {
                'email': send_email,
                'sms': send_sms,
                'telegram': send_telegram,
                'whatsapp': send_whatsapp,
            }
            dispatcher = dispatchers.get(channel)
            if not dispatcher:
                return {'status': 'failed', 'error': f'Unknown channel: {channel}'}
            return dispatcher(target, message)

        send_fn = default_send

    logger.info(f"Worker starting (poll_interval={poll_interval}s, batch_size={batch_size})")

    iteration = 0
    while True:
        iteration += 1
        if max_iterations > 0 and iteration > max_iterations:
            logger.info(f"Reached max iterations ({max_iterations}), stopping")
            break

        db = SessionLocal()
        try:
            tasks = fetch_pending_tasks(db, limit=batch_size)

            if not tasks:
                logger.debug(f"No tasks found, sleeping {poll_interval}s")
                time.sleep(poll_interval)
                continue

            logger.info(f"Processing {len(tasks)} tasks")

            for task in tasks:
                if not mark_task_processing(db, task.id):
                    logger.debug(f"Task {task.id} already taken, skipping")
                    continue

                logger.info(f"Processing task {task.id}: {task.channel} -> {task.target}")

                success, error = process_single_task(task, send_fn)

                if success:
                    mark_task_completed(db, task.id)
                    logger.info(f"Task {task.id} completed successfully")
                else:
                    mark_task_failed(db, task.id, error)
                    logger.warning(f"Task {task.id} failed: {error} (attempt {task.attempts + 1}/{task.max_attempts})")

        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
        finally:
            db.close()

        time.sleep(poll_interval)

    logger.info("Worker stopped")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Notification queue worker')
    parser.add_argument('--poll-interval', type=float, default=5.0, help='Seconds between queue polls')
    parser.add_argument('--batch-size', type=int, default=10, help='Max tasks per iteration')
    parser.add_argument('--max-iterations', type=int, default=0, help='Max iterations (0=forever)')
    args = parser.parse_args()

    run_worker(
        poll_interval=args.poll_interval,
        batch_size=args.batch_size,
        max_iterations=args.max_iterations,
    )


if __name__ == '__main__':
    main()
