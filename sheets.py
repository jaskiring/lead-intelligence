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


def normalize_refrens_csv(df: pd.DataFrame) -> pd.DataFrame:
    """Map Refrens CSV → internal schema"""

    mapped = pd.DataFrame()

    mapped["phone"] = (
        df.get("Phone")
        .fillna(df.get("phone_number"))
        .astype(str)
        .str.strip()
    )

    mapped["name"] = df.get("Contact Name", "")

    mapped["reason"] = df.get(
        "what_is_the_main_reason_you're_considering_lasik_surgery?"
    )

    mapped["timeline"] = df.get(
        "when_would_you_prefer_to_undergo_the_lasik_treatment?"
    )

    mapped["city"] = df.get("which_city_would_you_prefer_for_treatment_")

    mapped["objection_type"] = df.get("Objection Type")
    mapped["call_outcome"] = df.get("Call Outcome")
    mapped["consultation_status"] = df.get("Consultation Status")
    mapped["status"] = df.get("Status")

    return mapped


def load_leads(sheet):
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=INTERNAL_COLUMNS)
    return pd.DataFrame(records)


def upsert_leads(sheet, df: pd.DataFrame):
    existing = load_leads(sheet)

    if existing.empty:
        sheet.update(
            [INTERNAL_COLUMNS]
            + df.reindex(columns=INTERNAL_COLUMNS)
            .fillna("")
            .astype(str)
            .values.tolist()
        )
        return

    existing.set_index("phone", inplace=True)
    df.set_index("phone", inplace=True)

    for phone, row in df.iterrows():
        if phone in existing.index:
            row_idx = existing.index.get_loc(phone) + 2
            for col in INTERNAL_COLUMNS:
                sheet.update_cell(
                    row_idx,
                    INTERNAL_COLUMNS.index(col) + 1,
                    str(row.get(col, "")),
                )
        else:
            sheet.append_row(
                [row.get(col, "") for col in INTERNAL_COLUMNS]
            )


def atomic_pick(sheet, phone: str, rep_name: str):
    df = load_leads(sheet)

    if phone not in df["phone"].astype(str).values:
        return False, "Lead not found"

    row_idx = df.index[df["phone"].astype(str) == phone][0] + 2

    if str(df.loc[row_idx - 2, "picked"]).lower() == "true":
        return False, "Already picked"

    now = datetime.now(timezone.utc).isoformat()

    sheet.update_cell(row_idx, INTERNAL_COLUMNS.index("picked") + 1, "TRUE")
    sheet.update_cell(
        row_idx, INTERNAL_COLUMNS.index("picked_by") + 1, rep_name
    )
    sheet.update_cell(
        row_idx, INTERNAL_COLUMNS.index("picked_at") + 1, now
    )

    return True, "Picked"