import gspread
import pandas as pd
from datetime import datetime, timezone


def load_leads(sheet):
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def upsert_leads(sheet, df, lead_key="phone"):
    existing = sheet.get_all_records()
    existing_df = pd.DataFrame(existing)

    if existing_df.empty:
        sheet.update([df.columns.tolist()] + df.values.tolist())
        return

    existing_df.set_index(lead_key, inplace=True)
    df.set_index(lead_key, inplace=True)

    for key, row in df.iterrows():
        if key in existing_df.index:
            row_idx = existing_df.index.get_loc(key) + 2
            for col, val in row.items():
                col_idx = existing_df.columns.get_loc(col) + 2
                sheet.update_cell(row_idx, col_idx, val)
        else:
            sheet.append_row([row.get(col) for col in existing_df.columns])


def atomic_pick(sheet, phone, rep_name):
    records = sheet.get_all_records()
    df = pd.DataFrame(records)

    if df.empty or phone not in df["phone"].astype(str).values:
        return False, "Lead not found"

    row_idx = df.index[df["phone"].astype(str) == phone][0] + 2

    picked = df.loc[df.index[row_idx - 2], "picked"]
    if picked is True:
        picked_by = df.loc[df.index[row_idx - 2], "picked_by"]
        return False, f"Already picked by {picked_by}"

    sheet.update_cell(row_idx, df.columns.get_loc("picked") + 1, True)
    sheet.update_cell(row_idx, df.columns.get_loc("picked_by") + 1, rep_name)
    sheet.update_cell(
        row_idx,
        df.columns.get_loc("picked_at") + 1,
        datetime.now(timezone.utc).isoformat()
    )

    return True, "Picked successfully"