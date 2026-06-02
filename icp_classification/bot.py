"""
Slack bot for ICP Classification.
Uses Socket Mode (no public URL needed) — works from any machine.
All workspace members can DM the bot or @mention it in channels.
"""

import os
import re
import time
import logging
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

from enrichment import enrich_profile, is_linkedin_url
from classifier import classify_company, format_result_text, format_bulk_summary

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Slack app
app = App(token=os.getenv("SLACK_BOT_TOKEN"))


def parse_inputs(text: str) -> list[str]:
    """
    Parse user message into individual email/LinkedIn inputs.
    Supports:
    - Single email: john@acme.com
    - Single LinkedIn: linkedin.com/in/john
    - Bulk comma-separated: john@a.com, jane@b.com
    - Bulk newline-separated
    - Mixed: john@a.com, linkedin.com/in/jane
    """
    # Remove common filler words
    text = text.strip()

    # Remove bot mention patterns like <@U123ABC>
    text = re.sub(r"<@[A-Z0-9]+>", "", text)

    # Remove common prefixes people might use
    for prefix in ["classify", "check", "lookup", "look up", "score", "icp"]:
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
            # Remove leading colon or dash
            text = text.lstrip(":- ").strip()

    # Split by commas, newlines, or spaces (but not within emails/URLs)
    items = []
    
    def _clean_slack_link(s: str) -> str:
        s = s.strip().strip("<>")
        if "|" in s:
            s = s.split("|")[-1]
        return s.strip()

    for line in text.split("\n"):
        for part in line.split(","):
            part = part.strip()
            # Further split by whitespace, but keep URLs intact
            if " " in part and not is_linkedin_url(part):
                for subpart in part.split():
                    subpart = _clean_slack_link(subpart)
                    if "@" in subpart or is_linkedin_url(subpart):
                        items.append(subpart)
            else:
                part = _clean_slack_link(part)
                if part and ("@" in part or is_linkedin_url(part) or "linkedin.com" in part.lower()):
                    items.append(part)

    return items


def process_single(input_text: str) -> dict:
    """Enrich and classify a single input."""
    enriched = enrich_profile(input_text)
    result = classify_company(enriched)
    return result


@app.event("app_mention")
def handle_mention(event, say):
    """Handle @mentions in channels."""
    text = event.get("text", "")
    user = event.get("user", "")
    thread_ts = event.get("ts")  # Reply in thread

    inputs = parse_inputs(text)
    if not inputs:
        say(
            text="👋 Send me email addresses or LinkedIn URLs and I'll classify them against Zenskar's ICP.\n\n"
            "*Examples:*\n"
            "• `john@acme.com`\n"
            "• `https://linkedin.com/in/jane-doe`\n"
            "• Bulk: `john@a.com, jane@b.com, bob@c.com`",
            thread_ts=thread_ts,
        )
        return

    _process_and_respond(inputs, say, thread_ts, user)


@app.event("message")
def handle_dm(event, say):
    """Handle direct messages to the bot."""
    # Skip bot's own messages, message_changed events, etc.
    if event.get("subtype"):
        return

    text = event.get("text", "")
    user = event.get("user", "")

    # Check if this is a DM (channel starts with 'D')
    channel = event.get("channel", "")
    if not channel.startswith("D"):
        return  # Not a DM, and not a mention — ignore

    inputs = parse_inputs(text)
    if not inputs:
        say(
            text="👋 Hi! Send me email addresses or LinkedIn URLs and I'll classify them against Zenskar's ICP.\n\n"
            "*Examples:*\n"
            "• `john@acme.com`\n"
            "• `https://linkedin.com/in/jane-doe`\n"
            "• Bulk: paste multiple emails, one per line or comma-separated\n\n"
            "_I'll tell you if each company is a strong fit, partial fit, or not ICP._"
        )
        return

    _process_and_respond(inputs, say, None, user)


def _process_and_respond(inputs: list[str], say, thread_ts: str | None, user: str):
    """Process inputs and send classification results."""
    total = len(inputs)
    is_bulk = total > 1

    # Send processing indicator
    if is_bulk:
        say(text=f"⏳ Processing {total} profiles... this may take a moment.", thread_ts=thread_ts)
    else:
        say(text=f"⏳ Looking up `{inputs[0]}`...", thread_ts=thread_ts)

    results = []
    for i, input_text in enumerate(inputs):
        try:
            result = process_single(input_text)
            results.append(result)
            
            # If bulk, stream the result immediately so user doesn't wait
            if is_bulk:
                say(text=format_result_text(result), thread_ts=thread_ts)
                
        except Exception as e:
            logger.error(f"Error processing {input_text}: {e}")
            error_result = {
                "success": False,
                "error": str(e),
                "input": input_text,
            }
            results.append(error_result)
            if is_bulk:
                say(text=f"❗ Error processing `{input_text}`: {str(e)}", thread_ts=thread_ts)

    # Format and send final summary
    if is_bulk:
        say(text="*✅ All finished! Here is your summary:*", thread_ts=thread_ts)
        summary = format_bulk_summary(results)
        say(text=summary, thread_ts=thread_ts)
    else:
        # Single result — send full detail
        say(text=format_result_text(results[0]), thread_ts=thread_ts)


def start_bot():
    """Start the Slack bot in Socket Mode."""
    app_token = os.getenv("SLACK_APP_TOKEN")
    if not app_token:
        raise ValueError(
            "SLACK_APP_TOKEN not set. Create a Slack app with Socket Mode enabled "
            "and add the app-level token to your .env file."
        )

    bot_token = os.getenv("SLACK_BOT_TOKEN")
    if not bot_token:
        raise ValueError(
            "SLACK_BOT_TOKEN not set. Install the Slack app to your workspace "
            "and add the bot token to your .env file."
        )

    logger.info("🚀 ICP Classification Bot starting...")
    logger.info("   Bot is ready! Send DMs or @mention in channels.")
    handler = SocketModeHandler(app, app_token)
    handler.start()
