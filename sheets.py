import pandas as pd
from datetime import datetime, timezone

def load_leads(sheet):
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # ✅ NORMALIZE PICKED FIELD
    if "picked" in df.columns:
        df["picked"] = df["picked"].apply(
            lambda x: True if str(x).lower() in ["true", "1", "yes"] else False
        )

    return df


def upsert_leads(sheet, df, lead_key="phone"):
    existing = sheet.get_all_records()
    if not existing:
        sheet.update([df.columns.tolist()] + df.values.tolist())
        return

    existing_df = pd.DataFrame(existing)
    existing_df.set_index(lead_key, inplace=True)
    df = df.set_index(lead_key)

    for phone, row in df.iterrows():
        if phone in existing_df.index:
            row_idx = existing_df.index.get_loc(phone) + 2
            for col, val in row.items():
                col_idx = existing_df.columns.get_loc(col) + 1
                sheet.update_cell(row_idx, col_idx, val)
        else:
            sheet.append_row(row.tolist())


def atomic_pick(sheet, phone, rep_name):
    records = sheet.get_all_records()
    if not records:
        return False, "No data"

    df = pd.DataFrame(records)

    df["picked"] = df["picked"].apply(
        lambda x: True if str(x).lower() in ["true", "1", "yes"] else False
    )

    match = df[df["phone"].astype(str) == str(phone)]

    if match.empty:
        return False, "Lead not found"

    idx = match.index[0]

    if df.loc[idx, "picked"] is True:
        return False, f"Already picked by {df.loc[idx, 'picked_by']}"

    row_number = idx + 2

    sheet.update_cell(row_number, df.columns.get_loc("picked") + 1, True)
    sheet.update_cell(row_number, df.columns.get_loc("picked_by") + 1, rep_name)
    sheet.update_cell(
        row_number,
        df.columns.get_loc("picked_at") + 1,
        datetime.now(timezone.utc).isoformat()
    )

    return True, "Picked"