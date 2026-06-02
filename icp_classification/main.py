"""
ICP Classification Agent — Main entry point.

Usage:
    Slack bot mode:  python main.py
    CLI mode:        python main.py --cli john@acme.com jane@startup.io
    CLI bulk file:   python main.py --cli --file attendees.txt
"""

import sys
import argparse
import os
from dotenv import load_dotenv

load_dotenv()

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_cli(inputs: list[str]):
    """Run classification in CLI mode (no Slack needed)."""
    from enrichment import enrich_profile
    from classifier import classify_company, format_result_text, format_bulk_summary

    if not inputs:
        print("Usage: python main.py --cli email1@company.com email2@company.com")
        print("       python main.py --cli --file attendees.txt")
        sys.exit(1)

    print(f"\n🔍 Classifying {len(inputs)} profile(s)...\n")

    results = []
    for i, input_text in enumerate(inputs):
        input_text = input_text.strip()
        if not input_text:
            continue

        print(f"  [{i+1}/{len(inputs)}] Processing: {input_text}...")
        try:
            enriched = enrich_profile(input_text)
            result = classify_company(enriched)
            results.append(result)

            # Print individual result
            print(format_result_text(result))
            print("─" * 60)
        except Exception as e:
            print(f"  ❗ Error: {e}")
            results.append({"success": False, "error": str(e), "input": input_text})
            print("─" * 60)

    # Print summary if bulk
    if len(results) > 1:
        print("\n" + "═" * 60)
        print(format_bulk_summary(results))


def run_slack_bot():
    """Start the Slack bot."""
    from bot import start_bot
    start_bot()


def main():
    parser = argparse.ArgumentParser(description="Zenskar ICP Classification Agent")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode instead of Slack bot")
    parser.add_argument("--file", type=str, help="File with emails/LinkedIn URLs (one per line)")
    parser.add_argument("inputs", nargs="*", help="Email addresses or LinkedIn URLs to classify")

    args = parser.parse_args()

    if args.cli:
        inputs = list(args.inputs)

        # Read from file if provided
        if args.file:
            try:
                with open(args.file, "r") as f:
                    file_inputs = [line.strip() for line in f if line.strip()]
                inputs.extend(file_inputs)
            except FileNotFoundError:
                print(f"❗ File not found: {args.file}")
                sys.exit(1)

        run_cli(inputs)
    else:
        run_slack_bot()


if __name__ == "__main__":
    main()
