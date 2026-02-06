import pandas as pd
from datetime import datetime, timezone
import logging

# ---------------- LOGGING
logging.basicConfig(level=logging.INFO)
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

# Fields that admin upload MUST NOT overwrite
PROTECTED_FIELDS = {"picked", "picked_by", "picked_at"}

# ======================================================
# HELPERS
# ======================================================
def _safe(val):
    if pd.isna(val):
        return ""
    return str(val)


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    phone = str(phone).strip()
    if phone.endswith(".0"):
        phone = phone[:-2]
    return "".join(ch for ch in phone if ch.isdigit())


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
# LOAD LEADS (WITH ROW INDEX)
# ======================================================
def load_leads(sheet):
    rows = sheet.get_all_values()
    if len(rows) <= 1:
        return pd.DataFrame(columns=INTERNAL_COLUMNS + ["_row"])

    header = [h.strip().lower() for h in rows[0]]
    data = rows[1:]

    df = pd.DataFrame(data, columns=header)
    df["phone"] = df["phone"].apply(normalize_phone)
    df["_row"] = df.index + 2
    return df


# ======================================================
# UPSERT LEADS (SAFE)
# ======================================================
def upsert_leads(sheet, df: pd.DataFrame):
    df.columns = [c.strip().lower() for c in df.columns]
    df["phone"] = df["phone"].apply(normalize_phone)

    existing = load_leads(sheet)

    if existing.empty:
        sheet.update([INTERNAL_COLUMNS] + df.reindex(columns=INTERNAL_COLUMNS).fillna("").values.tolist())
        return

    existing.set_index("phone", inplace=True)
    df.set_index("phone", inplace=True)

    for phone, row in df.iterrows():
        if phone in existing.index:
            row_idx = int(existing.loc[phone, "_row"])

            for col in INTERNAL_COLUMNS:
                if col in PROTECTED_FIELDS:
                    continue  # 🔒 never overwrite ownership

                val = _safe(row.get(col))
                col_idx = INTERNAL_COLUMNS.index(col) + 1
                sheet.update_cell(row_idx, col_idx, val)

        else:
            # New lead → safe defaults
            new_row = []
            for col in INTERNAL_COLUMNS:
                if col in PROTECTED_FIELDS:
                    new_row.append("")
                else:
                    new_row.append(_safe(row.get(col)))
            sheet.append_row(new_row)


# ======================================================
# ATOMIC PICK (LOCK SAFE)
# ======================================================
def atomic_pick(sheet, phone: str, rep_name: str):
    phone = normalize_phone(phone)
    df = load_leads(sheet)

    match = df[df["phone"] == phone]
    if match.empty:
        return False, "Lead not found"

    row = match.iloc[0]
    if str(row.get("picked", "")).lower() == "true":
        return False, "Already picked"

    row_idx = int(row["_row"])
    now = datetime.now(timezone.utc).isoformat()

    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked") + 1, "TRUE")
    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked_by") + 1, rep_name)
    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked_at") + 1, now)

    return True, "Picked"