import pandas as pd
from datetime import datetime, timezone
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

INTERNAL_COLUMNS = [
    "phone",
    "name",
    "reason",
    "timeline",
    "city",
    "objection_type",
    "call_outcome",
    "consultation_status",
    "status",
    "intent_score",
    "intent_band",
    "lead_state",
    "picked",
    "picked_by",
    "picked_at",
    "last_refresh",
]


def _safe(val):
    if pd.isna(val):
        return ""
    return str(val)


def normalize_phone(phone) -> str:
    if phone is None:
        return ""
    phone = str(phone).strip()
    if phone.endswith(".0"):
        phone = phone[:-2]
    return "".join(ch for ch in phone if ch.isdigit())


# ======================================================
# LOAD LEADS (WITH SHEET ROW NUMBER)
# ======================================================
def load_leads(sheet):
    rows = sheet.get_all_values()  # includes header

    if len(rows) <= 1:
        return pd.DataFrame(columns=INTERNAL_COLUMNS + ["_row"])

    header = [h.strip().lower() for h in rows[0]]
    data = rows[1:]

    df = pd.DataFrame(data, columns=header)

    if "phone" not in df.columns:
        raise RuntimeError("phone column missing in sheet")

    df["phone"] = df["phone"].apply(normalize_phone)

    # 🔥 store actual sheet row number
    df["_row"] = df.index + 2

    log.info(
        "load_leads | phone+row sample = %s",
        df[["phone", "_row"]].head(5).values.tolist(),
    )

    return df


# ======================================================
# ATOMIC PICK (ROW-BASED, BULLETPROOF)
# ======================================================
def atomic_pick(sheet, phone: str, rep_name: str):
    phone = normalize_phone(phone)
    df = load_leads(sheet)

    match = df[df["phone"] == phone]

    if match.empty:
        log.error("atomic_pick | phone not found = %s", phone)
        return False, "Lead not found"

    row_idx = int(match.iloc[0]["_row"])

    if str(match.iloc[0].get("picked", "")).lower() == "true":
        return False, "Already picked"

    now = datetime.now(timezone.utc).isoformat()

    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked") + 1, "TRUE")
    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked_by") + 1, rep_name)
    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked_at") + 1, now)

    log.info("atomic_pick | success phone=%s row=%s", phone, row_idx)

    return True, "Picked"