import os
import sys
import yaml
import logging
import argparse
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from database import init_db, get_stats, get_jobs_by_status
from scraper import run_job_search
from applier import PlaywrightApplier
from matcher import evaluate_job_match
from dashboard import generate_dashboard

# Configure rich logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("job_hunter.scheduler")

CONFIG_PATH = Path(__file__).parent / "config.yaml"

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Configuration file not found at {CONFIG_PATH}")
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def run_job_cycle(config: dict, dry_run: bool = False):
    """
    Single cycle: Search -> Match -> Auto-Apply / Queue -> Report.
    """
    logger.info("=" * 60)
    logger.info(f"🔄 Starting Job Hunter Cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 1. Search for new listings across all configured platforms & roles
    new_jobs = run_job_search(config)
    logger.info(f"Discovered {len(new_jobs)} new listings in this cycle.")

    if dry_run:
        logger.info("🛠️ [DRY RUN MODE] Skipping application submissions.")
        return

    # 2. Process discovered jobs
    unprocessed = get_jobs_by_status("DISCOVERED", limit=50)
    if not unprocessed:
        logger.info("No new jobs to process.")
        return

    applier = PlaywrightApplier(config)
    applied_count = 0
    max_apps = config.get("schedule", {}).get("daily_max_applications", 20)

    for job in unprocessed:
        if applied_count >= max_apps:
            logger.warning(f"Reached safety limit of {max_apps} applications for this cycle.")
            break

        is_match, score, reason = evaluate_job_match(job, config)
        if not is_match:
            logger.info(f"Skipping non-matching job: '{job.get('title')}' ({reason})")
            continue

        logger.info(f"🎯 Target matched (score: {score:.1f}%): '{job.get('title')}' at '{job.get('company')}'")
        success = applier.apply_to_job(job)
        if success:
            applied_count += 1

    logger.info(f"Cycle completed. Successfully applied to {applied_count} jobs.")
    stats = get_stats()
    dash_path = generate_dashboard()
    logger.info(f"📊 Dashboard updated: {dash_path}")
    logger.info(f"📊 Current Overall Stats: {stats}")

def start_scheduler(config: dict, run_immediately: bool = True):
    """Start the recurring 12-hour scheduler."""
    interval_hours = config.get("schedule", {}).get("interval_hours", 12)
    scheduler = BlockingScheduler()

    # Schedule the recurring job every 12 hours
    scheduler.add_job(
        func=run_job_cycle,
        args=[config, False],
        trigger=IntervalTrigger(hours=interval_hours),
        id="job_hunter_cycle",
        name=f"Job Hunter Search & Apply every {interval_hours} hours",
        replace_existing=True
    )

    logger.info(f"⏱️ Job Hunter Scheduler activated! Running every {interval_hours} hours.")

    if run_immediately:
        logger.info("Triggering initial cycle now...")
        run_job_cycle(config, dry_run=False)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Platform Job Search & Auto-Apply Scheduler")
    parser.add_argument("--run-now", action="store_true", help="Run a single search and apply cycle immediately")
    parser.add_argument("--dry-run", action="store_true", help="Search and log matching jobs without applying")
    parser.add_argument("--stats", action="store_true", help="Display application stats and history")
    parser.add_argument("--daemon", action="store_true", help="Start recurring 12-hour background scheduler")

    args = parser.parse_args()
    init_db()
    cfg = load_config()

    if args.stats:
        stats = get_stats()
        print("\n=== Job Hunter Statistics ===")
        for status, count in stats.items():
            print(f"  {status:<15}: {count}")
        print("=============================\n")
    elif args.dry_run:
        run_job_cycle(cfg, dry_run=True)
    elif args.run_now:
        run_job_cycle(cfg, dry_run=False)
    else:
        # Default behavior: run immediately and schedule every 12 hours
        start_scheduler(cfg, run_immediately=True)
