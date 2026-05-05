"""
Google Sheets Writer
Writes classified events to a Google Sheet with rich formatting.
- Removes rows for past events on each run
- Appends all new events WITHOUT deduplication
- Applies header colors, alternating rows, score badges, event-type colors,
  column widths, frozen header, auto-filter, and hyperlinked registration URLs
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EVENT_HEADERS = [
    "Event Name",       # A  0
    "Host Company",     # B  1
    "Category",         # C  2
    "Event Type",       # D  3
    "Date",             # E  4
    "Location",         # F  5
    "Target Audience",  # G  6
    "Registration URL", # H  7
    "Description",      # I  8
    "Relevance Score",  # J  9
    "Source URL",       # K  10
    "Detected At",      # L  11
    "Status",           # M  12
]

NUM_COLS = len(EVENT_HEADERS)
DATE_COL     = EVENT_HEADERS.index("Date")
SCORE_COL    = EVENT_HEADERS.index("Relevance Score")
TYPE_COL     = EVENT_HEADERS.index("Event Type")
REG_URL_COL  = EVENT_HEADERS.index("Registration URL")

# Column widths in pixels
COLUMN_WIDTHS = [270, 145, 110, 125, 105, 175, 200, 175, 275, 85, 175, 145, 105]

# ── Palette ───────────────────────────────────────────────────────────────────
HEADER_BG  = "1F4E79"   # deep navy
HEADER_FG  = "FFFFFF"
BORDER_CLR = "C8D0DA"   # soft gray border
ROW_ALT_BG = "EDF3FB"   # very light steel-blue (even rows)

SCORE_HIGH = dict(bg="C6EFCE", fg="1E6B22")  # green  ≥ 8
SCORE_MED  = dict(bg="FFEB9C", fg="7D5700")  # amber  5–7
SCORE_LOW  = dict(bg="FFC7CE", fg="9C0006")  # red    ≤ 4

EVENT_TYPE_PALETTE = {
    "summit":     ("4472C4", "FFFFFF"),
    "conference": ("4472C4", "FFFFFF"),
    "dinner":     ("C0504D", "FFFFFF"),
    "roundtable": ("E36C09", "FFFFFF"),
    "meetup":     ("4BACC6", "FFFFFF"),
    "networking": ("4BACC6", "FFFFFF"),
    "workshop":   ("F79646", "FFFFFF"),
    "happy hour": ("70AD47", "FFFFFF"),
    "forum":      ("7030A0", "FFFFFF"),
    "panel":      ("5B9BD5", "FFFFFF"),
    "other":      ("808080", "FFFFFF"),
}


def _safe_hyperlink(url: str, label: str = "Register →") -> str:
    """Build a HYPERLINK formula with sanitized URL to prevent formula injection."""
    # Strip quotes and dangerous characters from URL
    sanitized = url.replace('"', "%22").replace("'", "%27")
    return f'=HYPERLINK("{sanitized}", "{label}")'


# ── Sheets API helpers ────────────────────────────────────────────────────────

def _rgb(hex_color: str) -> dict:
    """Hex string → Sheets API color dict (0–1 float scale)."""
    h = hex_color.lstrip("#")
    return {
        "red":   int(h[0:2], 16) / 255,
        "green": int(h[2:4], 16) / 255,
        "blue":  int(h[4:6], 16) / 255,
    }


def _repeat_cell(sheet_id: int, r1: int, r2: int, c1: int, c2: int,
                 fmt: dict, fields: str) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": r1, "endRowIndex": r2,
                "startColumnIndex": c1, "endColumnIndex": c2,
            },
            "cell": {"userEnteredFormat": fmt},
            "fields": f"userEnteredFormat({fields})",
        }
    }


def _col_width(sheet_id: int, col: int, px: int) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": px},
            "fields": "pixelSize",
        }
    }


def _row_height(sheet_id: int, r1: int, r2: int, px: int) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": r1, "endIndex": r2},
            "properties": {"pixelSize": px},
            "fields": "pixelSize",
        }
    }


def _cond_rule(sheet_id: int, r1: int, c1: int, c2: int,
               condition: dict, bg: str, fg: str, index: int) -> dict:
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": r1,
                    "startColumnIndex": c1,
                    "endColumnIndex": c2,
                }],
                "booleanRule": {
                    "condition": condition,
                    "format": {
                        "backgroundColor": _rgb(bg),
                        "textFormat": {"foregroundColor": _rgb(fg), "bold": True},
                    },
                },
            },
            "index": index,
        }
    }


def _get_cond_format_count(spreadsheet: gspread.Spreadsheet, sheet_id: int) -> int:
    """Return the number of existing conditional format rules for this sheet."""
    try:
        resp = spreadsheet.client.request(
            "GET",
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet.id}",
            params={"fields": "sheets(properties/sheetId,conditionalFormats)"},
        )
        for sheet in resp.json().get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") == sheet_id:
                return len(sheet.get("conditionalFormats", []))
    except Exception:
        pass
    return 0


# ── Core formatting ───────────────────────────────────────────────────────────

def _apply_formatting(spreadsheet: gspread.Spreadsheet,
                      ws: gspread.Worksheet,
                      total_rows: int) -> None:
    """
    Apply full sheet formatting via a single Sheets API batchUpdate call.
    total_rows = number of data rows (excluding header).
    """
    sid = ws.id
    end_row = 1 + total_rows  # 0-based exclusive end (header + data)
    reqs = []

    # ── 1. Column widths ──────────────────────────────────────────────────────
    for col, px in enumerate(COLUMN_WIDTHS[:NUM_COLS]):
        reqs.append(_col_width(sid, col, px))

    # ── 2. Row heights ────────────────────────────────────────────────────────
    reqs.append(_row_height(sid, 0, 1, 44))                  # header
    if total_rows > 0:
        reqs.append(_row_height(sid, 1, end_row, 80))        # data rows

    # ── 3. Header style ───────────────────────────────────────────────────────
    reqs.append(_repeat_cell(
        sid, 0, 1, 0, NUM_COLS,
        {
            "backgroundColor": _rgb(HEADER_BG),
            "textFormat": {
                "bold": True, "fontSize": 11,
                "foregroundColor": _rgb(HEADER_FG),
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
            "wrapStrategy": "WRAP",
        },
        "backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy",
    ))

    # ── 4. Freeze header + auto-filter ────────────────────────────────────────
    reqs.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sid,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })
    reqs.append({
        "setBasicFilter": {
            "filter": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": 0, "endRowIndex": max(end_row, 2),
                    "startColumnIndex": 0, "endColumnIndex": NUM_COLS,
                }
            }
        }
    })

    if total_rows > 0:
        # ── 5. Base data cell style ───────────────────────────────────────────
        thin = {"style": "SOLID", "width": 1, "color": _rgb(BORDER_CLR)}
        reqs.append(_repeat_cell(
            sid, 1, end_row, 0, NUM_COLS,
            {
                "textFormat": {"fontSize": 10},
                "verticalAlignment": "TOP",
                "wrapStrategy": "WRAP",
                "borders": {"top": thin, "bottom": thin, "left": thin, "right": thin},
            },
            "textFormat,verticalAlignment,wrapStrategy,borders",
        ))

        # ── 6. White base background for all data rows ────────────────────────
        reqs.append(_repeat_cell(
            sid, 1, end_row, 0, NUM_COLS,
            {"backgroundColor": _rgb("FFFFFF")},
            "backgroundColor",
        ))

        # ── 7. Column-specific alignment ──────────────────────────────────────
        for col in (DATE_COL, SCORE_COL, EVENT_HEADERS.index("Category"),
                    EVENT_HEADERS.index("Status")):
            reqs.append(_repeat_cell(
                sid, 1, end_row, col, col + 1,
                {"horizontalAlignment": "CENTER"},
                "horizontalAlignment",
            ))

        # ── 8. Event Name: bold ───────────────────────────────────────────────
        reqs.append(_repeat_cell(
            sid, 1, end_row, 0, 1,
            {"textFormat": {"bold": True, "fontSize": 10}},
            "textFormat",
        ))

        # ── 9. Relevance Score: bold + centered ───────────────────────────────
        reqs.append(_repeat_cell(
            sid, 1, end_row, SCORE_COL, SCORE_COL + 1,
            {"textFormat": {"bold": True, "fontSize": 11},
             "horizontalAlignment": "CENTER"},
            "textFormat,horizontalAlignment",
        ))

    # ── 10. Clear existing conditional format rules ───────────────────────────
    n_existing = _get_cond_format_count(spreadsheet, sid)
    for i in range(n_existing - 1, -1, -1):
        reqs.append({"deleteConditionalFormatRule": {"sheetId": sid, "index": i}})

    if total_rows > 0:
        # ── 11. Alternating row colors (conditional format) ───────────────────
        # Even rows (2, 4, 6…) get the light blue tint
        reqs.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sid,
                        "startRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": NUM_COLS,
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": "=ISEVEN(ROW())"}],
                        },
                        "format": {"backgroundColor": _rgb(ROW_ALT_BG)},
                    },
                },
                "index": 0,
            }
        })

        # ── 12. Relevance score color badges (whole row) ──────────────────────
        score_letter = chr(ord("A") + SCORE_COL)   # e.g. "J"
        for rule_idx, (formula, colors) in enumerate([
            (f"=${score_letter}2>=8", SCORE_HIGH),
            (f"=${score_letter}2>=5", SCORE_MED),
            (f"=${score_letter}2<5",  SCORE_LOW),
        ], start=1):
            reqs.append(_cond_rule(
                sid, 1, SCORE_COL, SCORE_COL + 1,
                {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": formula}]},
                colors["bg"], colors["fg"], rule_idx,
            ))

        # ── 13. Event type color badges ───────────────────────────────────────
        for rule_offset, (etype, (bg, fg)) in enumerate(EVENT_TYPE_PALETTE.items(), start=4):
            reqs.append(_cond_rule(
                sid, 1, TYPE_COL, TYPE_COL + 1,
                {
                    "type": "TEXT_CONTAINS",
                    "values": [{"userEnteredValue": etype.title()}],
                },
                bg, fg, rule_offset,
            ))

    spreadsheet.batch_update({"requests": reqs})


# ── Auth & worksheet helpers ──────────────────────────────────────────────────

def _get_client() -> gspread.Client:
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

    if creds_file and os.path.exists(creds_file):
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    elif creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)
    else:
        raise ValueError(
            "Google credentials not found. "
            "Set GOOGLE_CREDENTIALS_FILE or GOOGLE_CREDENTIALS_JSON env var."
        )
    return gspread.authorize(creds)


def _get_or_create_worksheet(spreadsheet: gspread.Spreadsheet,
                              name: str) -> gspread.Worksheet:
    try:
        return spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=2000, cols=NUM_COLS)
        ws.append_row(EVENT_HEADERS)
        return ws


def _is_past_event(date_str: str) -> bool:
    today = datetime.now(timezone.utc).date()
    raw = date_str.strip()
    if not raw or raw.upper() in ("TBD", "N/A", "UNKNOWN"):
        return False

    # For date ranges like "March 15-17, 2026" or "2026-03-15 to 2026-03-17",
    # extract the last date (end of range) to decide if the event has passed
    # Split on common range separators and try parsing each part
    parts = re.split(r"\s*(?:to|–|—|-(?=\s))\s*", raw)

    for part in reversed(parts):  # try last part first (end date of range)
        part = part.strip().rstrip(",.")
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y",
                    "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
            try:
                return datetime.strptime(part, fmt).date() < today
            except ValueError:
                continue

    # Try to find any year-month-day pattern in the string as a fallback
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if match:
        try:
            from datetime import date
            d = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            return d < today
        except ValueError:
            pass

    return False


def _has_valid_date(date_str: str) -> bool:
    """Check if a date string is a real, parseable date (not approximate/vague)."""
    raw = date_str.strip()
    if not raw or raw.upper() in ("TBD", "N/A", "UNKNOWN"):
        return False
    # Must contain at least a year
    if not re.search(r"\d{4}", raw):
        return False
    # Try parsing with known formats
    parts = re.split(r"\s*(?:to|–|—|-(?=\s))\s*", raw)
    for part in parts:
        part = part.strip().rstrip(",.")
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y",
                    "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
            try:
                datetime.strptime(part, fmt)
                return True
            except ValueError:
                continue
    # Regex fallback
    if re.search(r"\d{4}-\d{1,2}-\d{1,2}", raw):
        return True
    return False


def _remove_past_events(ws: gspread.Worksheet) -> int:
    all_values = ws.get_all_values()
    if len(all_values) <= 1:
        return 0

    headers = all_values[0]
    date_col = headers.index("Date") if "Date" in headers else DATE_COL

    to_delete = [
        idx + 2
        for idx, row in enumerate(all_values[1:])
        if len(row) > date_col
        and (
            # Remove past events
            (_is_past_event(row[date_col]) if (row[date_col] or "").strip() else False)
            # Remove rows with invalid/approximate dates (TBD, vague, unparseable)
            or not _has_valid_date(row[date_col])
        )
    ]
    if not to_delete:
        return 0

    # Batch delete: remove rows in descending order using a single batch request
    # Group consecutive rows into ranges for efficiency
    reqs = []
    for row_idx in reversed(to_delete):
        reqs.append({
            "deleteDimension": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "ROWS",
                    "startIndex": row_idx - 1,  # 0-based
                    "endIndex": row_idx,
                }
            }
        })
    ws.spreadsheet.batch_update({"requests": reqs})
    return len(to_delete)


# ── Public API ────────────────────────────────────────────────────────────────

def write_events_to_sheet(
    events: list[dict],
    sheet_id: str,
    worksheet_name: str = "Classified Events",
    dry_run: bool = False,
    _spreadsheet: gspread.Spreadsheet | None = None,
) -> tuple[int, gspread.Spreadsheet]:
    """
    Write events to a Google Sheet worksheet with rich formatting.

    - Past events in the sheet are deleted first.
    - All provided events are appended without deduplication.
    - Sheet formatting (colors, widths, badges) is re-applied after each write.

    Returns a tuple of (number of events appended, spreadsheet object for reuse).
    """
    if _spreadsheet is not None:
        spreadsheet = _spreadsheet
    else:
        client = _get_client()
        spreadsheet = client.open_by_key(sheet_id)
    ws = _get_or_create_worksheet(spreadsheet, worksheet_name)

    # ── Remove past events ────────────────────────────────────────────────────
    if not dry_run:
        removed = _remove_past_events(ws)
        if removed:
            print(f"[Sheets] Removed {removed} past events from '{worksheet_name}'")
    else:
        print(f"[Sheets][DryRun] Would remove past events from '{worksheet_name}'")

    if not events:
        # Still re-apply formatting so the header looks clean even with no data
        if not dry_run:
            existing_rows = max(0, len(ws.get_all_values()) - 1)
            _apply_formatting(spreadsheet, ws, existing_rows)
        return 0, spreadsheet

    if dry_run:
        for event in events:
            print(
                f"  [Sheets][DryRun] Would add: "
                f"{event.get('event_name')} | {event.get('location', '?')} | "
                f"relevance:{event.get('relevance_score', '?')}"
            )
        return len(events), spreadsheet

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    is_linkedin = "linkedin" in worksheet_name.lower()
    status_label = "New (LinkedIn)" if is_linkedin else "New"

    # ── Dedup: build set of existing (event_name, date) pairs ──────────────
    all_values = ws.get_all_values()
    headers = all_values[0] if all_values else EVENT_HEADERS
    name_col = headers.index("Event Name") if "Event Name" in headers else 0
    date_col_idx = headers.index("Date") if "Date" in headers else DATE_COL
    existing_keys = set()
    for row in all_values[1:]:
        if len(row) > max(name_col, date_col_idx):
            key = (row[name_col].strip().lower(), row[date_col_idx].strip().lower())
            existing_keys.add(key)

    rows = []
    skipped_dupes = 0
    for event in events:
        event_name = event.get("event_name", "")
        event_date = event.get("date", "")
        dedup_key = (event_name.strip().lower(), event_date.strip().lower())
        if dedup_key in existing_keys:
            skipped_dupes += 1
            continue
        existing_keys.add(dedup_key)  # also dedup within the current batch

        reg_url = event.get("registration_url", "")
        reg_cell = (
            _safe_hyperlink(reg_url) if reg_url and reg_url.startswith("http")
            else reg_url
        )
        rows.append([
            event_name,
            event.get("host_company", ""),
            event.get("source_category", ""),
            event.get("event_type", ""),
            event_date,
            event.get("location", ""),
            event.get("target_audience", ""),
            reg_cell,
            event.get("description", ""),
            event.get("relevance_score", 0),
            event.get("source_url", ""),
            now,
            status_label,
        ])

    if skipped_dupes:
        print(f"[Sheets] Skipped {skipped_dupes} duplicate events in '{worksheet_name}'")

    if not rows:
        print(f"[Sheets] No new events to append to '{worksheet_name}'")
        total_data_rows = max(0, len(all_values) - 1)
        _apply_formatting(spreadsheet, ws, total_data_rows)
        return 0, spreadsheet

    ws.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"[Sheets] Appended {len(rows)} new events to '{worksheet_name}'")

    # ── Apply formatting ──────────────────────────────────────────────────────
    total_data_rows = len(ws.get_all_values()) - 1  # re-read after append
    print(f"[Sheets] Applying formatting ({total_data_rows} data rows)...")
    _apply_formatting(spreadsheet, ws, total_data_rows)
    print(f"[Sheets] Formatting applied to '{worksheet_name}'")

    return len(rows), spreadsheet


# ── Engagers sheet ───────────────────────────────────────────────────────────

ENGAGER_HEADERS = [
    "Name",           # A
    "LinkedIn URL",   # B
    "Title",          # C
    "Company",        # D
    "Email",          # E
    "Company Size",   # F
    "Industry",       # G
    "Location",       # H
    "ICP Score",      # I
    "Engagement Type", # J
    "Comment Text",   # K
    "Source Post",    # L
    "Source Company", # M
    "Enriched At",    # N
]

ENGAGER_COL_WIDTHS = [180, 200, 180, 180, 220, 100, 150, 170, 80, 110, 250, 200, 140, 140]
ENGAGER_NUM_COLS = len(ENGAGER_HEADERS)
ENGAGER_SCORE_COL = ENGAGER_HEADERS.index("ICP Score")

# ICP score thresholds for engagers
ENGAGER_SCORE_HIGH = dict(bg="C6EFCE", fg="1E6B22")  # green >= 70
ENGAGER_SCORE_MED  = dict(bg="FFEB9C", fg="7D5700")  # amber 50-69
ENGAGER_SCORE_LOW  = dict(bg="FFC7CE", fg="9C0006")  # red   < 50


def _apply_engager_formatting(spreadsheet: gspread.Spreadsheet,
                               ws: gspread.Worksheet,
                               total_rows: int) -> None:
    """Apply formatting to the Engagers sheet."""
    sid = ws.id
    end_row = 1 + total_rows
    reqs = []

    # Column widths
    for col, px in enumerate(ENGAGER_COL_WIDTHS[:ENGAGER_NUM_COLS]):
        reqs.append(_col_width(sid, col, px))

    # Row heights
    reqs.append(_row_height(sid, 0, 1, 44))
    if total_rows > 0:
        reqs.append(_row_height(sid, 1, end_row, 65))

    # Header style (green)
    reqs.append(_repeat_cell(
        sid, 0, 1, 0, ENGAGER_NUM_COLS,
        {
            "backgroundColor": _rgb("2E7D32"),
            "textFormat": {
                "bold": True, "fontSize": 11,
                "foregroundColor": _rgb("FFFFFF"),
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
            "wrapStrategy": "WRAP",
        },
        "backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy",
    ))

    # Freeze header + auto-filter
    reqs.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sid,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })
    reqs.append({
        "setBasicFilter": {
            "filter": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": 0, "endRowIndex": max(end_row, 2),
                    "startColumnIndex": 0, "endColumnIndex": ENGAGER_NUM_COLS,
                }
            }
        }
    })

    if total_rows > 0:
        # Base data cell style
        thin = {"style": "SOLID", "width": 1, "color": _rgb(BORDER_CLR)}
        reqs.append(_repeat_cell(
            sid, 1, end_row, 0, ENGAGER_NUM_COLS,
            {
                "textFormat": {"fontSize": 10},
                "verticalAlignment": "TOP",
                "wrapStrategy": "WRAP",
                "borders": {"top": thin, "bottom": thin, "left": thin, "right": thin},
            },
            "textFormat,verticalAlignment,wrapStrategy,borders",
        ))

        # White base background
        reqs.append(_repeat_cell(
            sid, 1, end_row, 0, ENGAGER_NUM_COLS,
            {"backgroundColor": _rgb("FFFFFF")},
            "backgroundColor",
        ))

        # Alternating rows
        reqs.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sid,
                        "startRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": ENGAGER_NUM_COLS,
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": "=ISEVEN(ROW())"}],
                        },
                        "format": {"backgroundColor": _rgb("E8F5E9")},
                    },
                },
                "index": 0,
            }
        })

        # ICP score badges
        score_letter = chr(ord("A") + ENGAGER_SCORE_COL)
        for rule_idx, (formula, colors) in enumerate([
            (f"=${score_letter}2>=70", ENGAGER_SCORE_HIGH),
            (f"=${score_letter}2>=50", ENGAGER_SCORE_MED),
            (f"=${score_letter}2<50",  ENGAGER_SCORE_LOW),
        ], start=1):
            reqs.append(_cond_rule(
                sid, 1, ENGAGER_SCORE_COL, ENGAGER_SCORE_COL + 1,
                {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": formula}]},
                colors["bg"], colors["fg"], rule_idx,
            ))

        # Name column: bold
        reqs.append(_repeat_cell(
            sid, 1, end_row, 0, 1,
            {"textFormat": {"bold": True, "fontSize": 10}},
            "textFormat",
        ))

        # ICP Score: bold + centered
        reqs.append(_repeat_cell(
            sid, 1, end_row, ENGAGER_SCORE_COL, ENGAGER_SCORE_COL + 1,
            {"textFormat": {"bold": True, "fontSize": 11},
             "horizontalAlignment": "CENTER"},
            "textFormat,horizontalAlignment",
        ))

    spreadsheet.batch_update({"requests": reqs})


def _get_or_create_engager_worksheet(
    spreadsheet: gspread.Spreadsheet,
    name: str,
) -> gspread.Worksheet:
    """Get or create a worksheet with engager headers."""
    try:
        return spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=2000, cols=ENGAGER_NUM_COLS)
        ws.append_row(ENGAGER_HEADERS)
        return ws


def write_engagers_to_sheet(
    engagers: list[dict],
    sheet_id: str,
    worksheet_name: str = "Engagers",
    dry_run: bool = False,
    _spreadsheet: gspread.Spreadsheet | None = None,
) -> tuple[int, gspread.Spreadsheet]:
    """
    Write enriched engagers to a Google Sheet worksheet.
    Clears and rewrites the sheet on each run (engagers change between runs).

    Returns (count_written, spreadsheet_object).
    """
    if _spreadsheet is not None:
        spreadsheet = _spreadsheet
    else:
        client = _get_client()
        spreadsheet = client.open_by_key(sheet_id)

    ws = _get_or_create_engager_worksheet(spreadsheet, worksheet_name)

    if dry_run:
        for eng in engagers:
            print(f"  [Sheets][DryRun] Would add engager: {eng.get('name')} "
                  f"({eng.get('title', eng.get('parsed_title', '?'))}) "
                  f"[ICP: {eng.get('icp_score', '?')}]")
        return len(engagers), spreadsheet

    # Clear existing data (keep header)
    ws.clear()
    ws.append_row(ENGAGER_HEADERS)

    if not engagers:
        _apply_engager_formatting(spreadsheet, ws, 0)
        print(f"[Sheets] No engagers to write to '{worksheet_name}'")
        return 0, spreadsheet

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = []
    for eng in engagers:
        linkedin_url = eng.get("linkedin_url", "")
        url_cell = (
            _safe_hyperlink(linkedin_url, "Profile →")
            if linkedin_url and linkedin_url.startswith("http")
            else linkedin_url
        )
        source_url = eng.get("source_post_url", "")
        source_cell = (
            _safe_hyperlink(source_url, "Post →")
            if source_url and source_url.startswith("http")
            else source_url
        )
        rows.append([
            eng.get("name", ""),
            url_cell,
            eng.get("title", "") or eng.get("parsed_title", ""),
            eng.get("company", "") or eng.get("parsed_company", ""),
            eng.get("email", ""),
            eng.get("company_size", ""),
            eng.get("industry", ""),
            eng.get("location", ""),
            eng.get("icp_score", 0),
            eng.get("engagement_type", ""),
            eng.get("comment_text", "")[:200],
            source_cell,
            eng.get("source_post_company", ""),
            now,
        ])

    ws.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"[Sheets] Wrote {len(rows)} engagers to '{worksheet_name}'")

    _apply_engager_formatting(spreadsheet, ws, len(rows))
    print(f"[Sheets] Formatting applied to '{worksheet_name}'")

    return len(rows), spreadsheet


# ── Location-based sheets ─────────────────────────────────────────────────────

# Sheets that should never be treated as location sheets
_SYSTEM_SHEETS = {"Classified Events", "LinkedIn Events", "Scraped Data", "Engagers"}

_SKIP_LOCATION_TERMS = {
    "not specified", "unknown", "tbd", "n/a", "virtual", "online",
    "location not", "to be determined", "venue tbd", "not disclosed",
    "implied", "city not", "city unknown",
}

_CITY_ALIASES = {
    "new york city": "New York",
    "nyc": "New York",
    "sf": "San Francisco",
    "san francisco bay area": "San Francisco",
}


def _extract_city(location: str) -> str | None:
    """
    Extract a clean city name from a raw location string.
    Returns None for virtual/unspecified locations.
    """
    if not location:
        return None
    loc = location.strip()
    if any(term in loc.lower() for term in _SKIP_LOCATION_TERMS):
        return None

    # Take text before the first comma
    city = loc.split(",")[0].strip()
    # Strip parenthetical venue details e.g. "Berlin (AchtBerlin)"
    city = re.sub(r"\s*\(.*?\)", "", city).strip()
    # Normalize known aliases
    city_lower = city.lower()
    city = _CITY_ALIASES.get(city_lower, city)
    # Sheet names can't be empty or >100 chars
    city = city[:50].strip()
    return city if city else None


def write_events_by_location(
    events: list[dict],
    sheet_id: str,
    dry_run: bool = False,
    _spreadsheet: gspread.Spreadsheet | None = None,
) -> None:
    """
    Write a separate worksheet tab per city, containing only that city's events.

    - Old location tabs that no longer have events are deleted.
    - Each tab is fully cleared and rewritten on every run (no past-event logic
      needed since the data is always rebuilt from scratch).
    - Same rich formatting as the main Classified Events sheet.
    """
    # Group events by city
    city_events: dict[str, list[dict]] = {}
    for event in events:
        city = _extract_city(event.get("location", ""))
        if city:
            city_events.setdefault(city, []).append(event)

    if not city_events:
        print("[Sheets] No events with known locations — skipping location sheets")
        return

    if dry_run:
        for city, evts in sorted(city_events.items()):
            print(f"  [Sheets][DryRun] Would create sheet '{city}' with {len(evts)} events")
        return

    if _spreadsheet is not None:
        spreadsheet = _spreadsheet
    else:
        client = _get_client()
        spreadsheet = client.open_by_key(sheet_id)
    existing = {ws.title: ws for ws in spreadsheet.worksheets()}

    # ── Delete stale location sheets ──────────────────────────────────────────
    for name, ws in existing.items():
        if name not in _SYSTEM_SHEETS and name not in city_events:
            spreadsheet.del_worksheet(ws)
            print(f"[Sheets] Deleted stale location sheet '{name}'")

    # ── Write each city ───────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    for city, city_event_list in sorted(city_events.items()):
        # Refresh existing map (may have changed after deletions)
        existing = {ws.title: ws for ws in spreadsheet.worksheets()}

        if city in existing:
            ws = existing[city]
            ws.clear()
            ws.append_row(EVENT_HEADERS)
        else:
            ws = spreadsheet.add_worksheet(title=city, rows=500, cols=NUM_COLS)
            ws.append_row(EVENT_HEADERS)

        rows = []
        for event in city_event_list:
            reg_url = event.get("registration_url", "")
            reg_cell = (
                f'=HYPERLINK("{reg_url}", "Register →")' if reg_url and reg_url.startswith("http")
                else reg_url
            )
            is_linkedin = "linkedin" in (event.get("status", "")).lower() or \
                          "linkedin" in (event.get("source_url", "")).lower()
            rows.append([
                event.get("event_name", ""),
                event.get("host_company", ""),
                event.get("source_category", ""),
                event.get("event_type", ""),
                event.get("date", ""),
                event.get("location", ""),
                event.get("target_audience", ""),
                reg_cell,
                event.get("description", ""),
                event.get("relevance_score", 0),
                event.get("source_url", ""),
                now,
                "New (LinkedIn)" if is_linkedin else "New",
            ])

        ws.append_rows(rows, value_input_option="USER_ENTERED")
        _apply_formatting(spreadsheet, ws, len(rows))
        print(f"[Sheets] '{city}': {len(rows)} event(s) written")
