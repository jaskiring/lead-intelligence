import pandas as pd
from datetime import datetime, timezone
import gspread

# -----------------------
# LOAD
# -----------------------
def load_leads(sheet):
    records = sheet.get_all_records()
    return pd.DataFrame(records)

# -----------------------
# UPSERT
# -----------------------
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
                col_idx = existing_df.columns.get_loc(col) + 1
                sheet.update_cell(row_idx, col_idx, val)
        else:
            sheet.append_row(row.tolist())

# -----------------------
# ATOMIC PICK (CRITICAL)
# -----------------------
def atomic_pick(sheet, phone, rep_name):
    records = sheet.get_all_records()
    df = pd.DataFrame(records)

    if df.empty or phone not in df["phone"].astype(str).values:
        return False, "Lead not found"

    row_idx = df.index[df["phone"].astype(str) == phone][0] + 2

    picked = df.loc[df["phone"].astype(str) == phone, "picked"].values[0]

    if picked is True:
        return False, "Lead already picked"

    sheet.update_cell(row_idx, df.columns.get_loc("picked") + 1, True)
    sheet.update_cell(row_idx, df.columns.get_loc("picked_by") + 1, rep_name)
    sheet.update_cell(
        row_idx,
        df.columns.get_loc("picked_at") + 1,
        datetime.now(timezone.utc).isoformat()
    )

    return True, "Picked"