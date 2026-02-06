import pandas as pd
from datetime import datetime, timezone
import logging

# ---------------- LOGGING
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

# ---------------- SCHEMA
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


# ======================================================
# HELPERS
# ======================================================
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

    phone = "".join(ch for ch in phone if ch.isdigit())
    return phone


# ======================================================
# NORMALIZE REFRENS CSV
# ======================================================
def normalize_refrens_csv(df: pd.DataFrame) -> pd.DataFrame:
    if "Phone" not in df.columns:
        raise ValueError("CSV must contain column 'Phone'")

    out = pd.DataFrame()

    out["phone"] = df["Phone"].apply(normalize_phone)
    out["name"] = df.get("Contact Name", "")
    out["reason"] = df.get(
        "what_is_the_main_reason_you're_considering_lasik_surgery?", ""
    )
    out["timeline"] = df.get(
        "when_would_you_prefer_to_undergo_the_lasik_treatment?", ""
    )
    out["city"] = df.get(
        "which_city_would_you_prefer_for_treatment_", ""
    )
    out["objection_type"] = df.get("Objection Type", "")
    out["call_outcome"] = df.get("Call Outcome", "")
    out["consultation_status"] = df.get("Consultation Status", "")
    out["status"] = df.get("Status", "")

    return out


# ======================================================
# LOAD LEADS (WITH SHEET ROW NUMBER)
# ======================================================
def load_leads(sheet):
    rows = sheet.get_all_values()

    if len(rows) <= 1:
        return pd.DataFrame(columns=INTERNAL_COLUMNS + ["_row"])

    header = [h.strip().lower() for h in rows[0]]
    data = rows[1:]

    df = pd.DataFrame(data, columns=header)

    if "phone" not in df.columns:
        raise RuntimeError("phone column missing in sheet")

    df["phone"] = df["phone"].apply(normalize_phone)

    # actual Google Sheet row number
    df["_row"] = df.index + 2

    return df


# ======================================================
# UPSERT LEADS
# ======================================================
def upsert_leads(sheet, df: pd.DataFrame):
    df.columns = [c.strip().lower() for c in df.columns]

    if "phone" not in df.columns:
        raise ValueError("phone column missing before upsert")

    df["phone"] = df["phone"].apply(normalize_phone)
    df = df.reindex(columns=INTERNAL_COLUMNS)
    df = df.applymap(_safe)

    existing = load_leads(sheet)

    if existing.empty:
        sheet.update([INTERNAL_COLUMNS] + df.values.tolist())
        return

    existing = existing.applymap(_safe)
    existing["phone"] = existing["phone"].apply(normalize_phone)

    existing.set_index("phone", inplace=True)
    df.set_index("phone", inplace=True)

    for phone, row in df.iterrows():
        row_values = [_safe(row.get(col)) for col in INTERNAL_COLUMNS]

        if phone in existing.index:
            row_idx = int(existing.loc[phone, "_row"])
            for col_idx, val in enumerate(row_values, start=1):
                sheet.update_cell(row_idx, col_idx, val)
        else:
            sheet.append_row(row_values)


# ======================================================
# ATOMIC PICK (ROW-BASED)
# ======================================================
def atomic_pick(sheet, phone: str, rep_name: str):
    phone = normalize_phone(phone)
    df = load_leads(sheet)

    match = df[df["phone"] == phone]

    if match.empty:
        return False, "Lead not found"

    row_idx = int(match.iloc[0]["_row"])

    if str(match.iloc[0].get("picked", "")).lower() == "true":
        return False, "Already picked"

    now = datetime.now(timezone.utc).isoformat()

    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked") + 1, "TRUE")
    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked_by") + 1, rep_name)
    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked_at") + 1, now)

    return True, "Picked"