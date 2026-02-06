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


def _safe(val):
    """Convert ANY value to a safe string for Google Sheets"""
    if pd.isna(val):
        return ""
    return str(val)


# ======================================================
# NORMALIZE REFRENS CSV
# ======================================================
def normalize_refrens_csv(df: pd.DataFrame) -> pd.DataFrame:
    log.info("normalize_csv | incoming columns = %s", list(df.columns))

    if "Phone" not in df.columns:
        log.error("❌ normalize_csv | 'Phone' column missing")
        raise ValueError("CSV must contain column 'Phone'")

    out = pd.DataFrame()

    out["phone"] = (
        df["Phone"]
        .astype(str)
        .str.replace(".0", "", regex=False)
        .str.strip()
    )

    log.info(
        "normalize_csv | phone sample = %s",
        out["phone"].head(5).tolist(),
    )

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
# LOAD LEADS FROM GOOGLE SHEET
# ======================================================
def load_leads(sheet):
    records = sheet.get_all_records()
    log.info("load_leads | record count = %s", len(records))

    if not records:
        log.warning("load_leads | no records found")
        return pd.DataFrame(columns=INTERNAL_COLUMNS)

    df = pd.DataFrame(records)

    log.info("load_leads | raw columns = %s", list(df.columns))

    # 🔥 normalize headers (CRITICAL)
    df.columns = [c.strip().lower() for c in df.columns]

    log.info("load_leads | normalized columns = %s", list(df.columns))

    if "phone" not in df.columns:
        log.error("❌ load_leads | phone column MISSING after normalization")
    else:
        log.info(
            "✅ load_leads | phone sample = %s",
            df["phone"].head(5).astype(str).tolist(),
        )

    return df


# ======================================================
# UPSERT LEADS
# ======================================================
def upsert_leads(sheet, df: pd.DataFrame):
    log.info("upsert | incoming df columns = %s", list(df.columns))

    # normalize headers
    df.columns = [c.strip().lower() for c in df.columns]

    if "phone" not in df.columns:
        log.critical("❌ upsert | phone column missing BEFORE reindex")
        raise ValueError("phone column missing before reindex")

    log.info(
        "upsert | phone sample BEFORE reindex = %s",
        df["phone"].head(5).tolist(),
    )

    df = df.reindex(columns=INTERNAL_COLUMNS)

    log.info(
        "upsert | phone sample AFTER reindex = %s",
        df["phone"].head(5).tolist(),
    )

    df = df.applymap(_safe)

    existing = load_leads(sheet)

    if existing.empty:
        log.warning("upsert | sheet empty, writing full data")
        sheet.update([INTERNAL_COLUMNS] + df.values.tolist())
        return

    existing = existing.applymap(_safe)
    existing.set_index("phone", inplace=True)
    df.set_index("phone", inplace=True)

    for phone, row in df.iterrows():
        row_values = [_safe(row.get(col)) for col in INTERNAL_COLUMNS]

        if phone in existing.index:
            row_idx = existing.index.get_loc(phone) + 2
            log.info("upsert | updating phone=%s at row=%s", phone, row_idx)
            for col_idx, val in enumerate(row_values, start=1):
                sheet.update_cell(row_idx, col_idx, val)
        else:
            log.info("upsert | inserting new phone=%s", phone)
            sheet.append_row(row_values)


# ======================================================
# ATOMIC PICK
# ======================================================
def atomic_pick(sheet, phone: str, rep_name: str):
    df = load_leads(sheet)
    df["phone"] = df["phone"].astype(str)

    log.info("atomic_pick | attempting phone=%s", phone)

    if phone not in df["phone"].values:
        log.error("atomic_pick | phone not found")
        return False, "Lead not found"

    row_idx = df.index[df["phone"] == phone][0] + 2

    if str(df.loc[row_idx - 2, "picked"]).lower() == "true":
        log.warning("atomic_pick | already picked")
        return False, "Already picked"

    now = datetime.now(timezone.utc).isoformat()

    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked") + 1, "TRUE")
    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked_by") + 1, rep_name)
    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked_at") + 1, now)

    log.info("atomic_pick | success phone=%s", phone)

    return True, "Picked"