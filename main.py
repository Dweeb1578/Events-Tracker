"""
Zenskar Event Detection System
CLI entry point for running the multi-agent event detection pipeline.

Usage:
    python main.py                    # Run once now
    python main.py --schedule daily   # Run daily at 9 AM
    python main.py --dry-run          # Preview without writing to Excel
    python main.py --min-relevance 7  # Only show highly relevant events
"""

import argparse
import logging
import sys
import time

# Force UTF-8 output on Windows to handle emoji in print statements
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

import schedule

from agents.orchestrator import run_pipeline


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/pipeline.log", mode="a", encoding="utf-8"),
        ],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Zenskar Event Detection System - Detect finance events from competitor companies",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview detected events without writing to Excel",
    )
    parser.add_argument(
        "--schedule",
        choices=["daily", "weekly"],
        help="Run on a schedule instead of once",
    )
    parser.add_argument(
        "--time",
        default="09:00",
        help="Time to run scheduled job (HH:MM format, default: 09:00)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to companies YAML config file",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to output Excel file",
    )
    parser.add_argument(
        "--min-relevance",
        type=int,
        default=5,
        help="Minimum relevance score (1-10, default: 5)",
    )
    parser.add_argument(
        "--include-google",
        action="store_true",
        help="Include Google search URLs (often blocked, disabled by default)",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Skip scraping, reuse previously cached scraped data (from output/scraped_cache.json)",
    )
    parser.add_argument(
        "--skip-linkedin",
        action="store_true",
        help="Skip LinkedIn post scraping via Apify (useful if no APIFY_API_TOKEN set)",
    )
    parser.add_argument(
        "--skip-luma",
        action="store_true",
        help="Skip Luma discover page scraping",
    )
    parser.add_argument(
        "--location",
        action="append",
        dest="locations",
        metavar="LOCATION",
        help=(
            "Only include events in this location (substring match, case-insensitive). "
            "Can be specified multiple times, e.g. --location 'San Francisco' --location 'New York'"
        ),
    )
    parser.add_argument(
        "--sheet-id",
        default=None,
        help=(
            "Google Spreadsheet ID to write events to. "
            "Falls back to GOOGLE_SHEET_ID env var if not set."
        ),
    )

    args = parser.parse_args()

    # Ensure logs directory exists
    import os
    os.makedirs("logs", exist_ok=True)

    setup_logging()

    def job():
        run_pipeline(
            config_path=args.config,
            output_path=args.output,
            dry_run=args.dry_run,
            skip_google=not args.include_google,
            min_relevance=args.min_relevance,
            use_cache=args.use_cache,
            skip_linkedin=args.skip_linkedin,
            skip_luma=args.skip_luma,
            locations=args.locations or [],
            sheet_id=args.sheet_id,
        )

    if args.schedule:
        print(f"📅 Scheduling pipeline to run {args.schedule} at {args.time}")

        if args.schedule == "daily":
            schedule.every().day.at(args.time).do(job)
        elif args.schedule == "weekly":
            schedule.every().monday.at(args.time).do(job)

        # Run once immediately, then on schedule
        print("Running initial scan now...")
        job()

        print(f"\n⏰ Next run scheduled. Waiting...")
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        # Single run
        job()


if __name__ == "__main__":
    main()
