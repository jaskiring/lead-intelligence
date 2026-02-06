import pandas as pd
from datetime import datetime, timezone

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


def normalize_refrens_csv(df: pd.DataFrame) -> pd.DataFrame:
    if "Phone" not in df.columns:
        raise ValueError("CSV must contain column 'Phone'")

    out = pd.DataFrame()

    out["phone"] = df["Phone"].astype(str).str.strip()
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


def load_leads(sheet):
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=INTERNAL_COLUMNS)
    return pd.DataFrame(records)


def upsert_leads(sheet, df: pd.DataFrame):
    df = df.reindex(columns=INTERNAL_COLUMNS)

    # 🔴 SANITIZE EVERYTHING
    df = df.applymap(_safe)

    existing = load_leads(sheet)

    if existing.empty:
        sheet.update(
            [INTERNAL_COLUMNS] + df.values.tolist()
        )
        return

    existing = existing.applymap(_safe)
    existing.set_index("phone", inplace=True)
    df.set_index("phone", inplace=True)

    for phone, row in df.iterrows():
        row_values = [_safe(row.get(col)) for col in INTERNAL_COLUMNS]

        if phone in existing.index:
            row_idx = existing.index.get_loc(phone) + 2
            for col_idx, val in enumerate(row_values, start=1):
                sheet.update_cell(row_idx, col_idx, val)
        else:
            sheet.append_row(row_values)


def atomic_pick(sheet, phone: str, rep_name: str):
    df = load_leads(sheet)

    df["phone"] = df["phone"].astype(str)

    if phone not in df["phone"].values:
        return False, "Lead not found"

    row_idx = df.index[df["phone"] == phone][0] + 2

    if str(df.loc[row_idx - 2, "picked"]).lower() == "true":
        return False, "Already picked"

    now = datetime.now(timezone.utc).isoformat()

    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked") + 1, "TRUE")
    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked_by") + 1, rep_name)
    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked_at") + 1, now)

    return True, "Picked"