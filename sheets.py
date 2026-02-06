import pandas as pd
from datetime import datetime
import gspread

# ---------------------------
# LOAD LEADS
# ---------------------------
def load_leads(sheet):
    records = sheet.get_all_records()
    return pd.DataFrame(records)

# ---------------------------
# UPSERT LEADS (SCHEMA SAFE)
# ---------------------------
def upsert_leads(sheet, df, lead_key="phone"):
    existing = sheet.get_all_records()
    existing_df = pd.DataFrame(existing)

    # If sheet empty → write headers + data
    if existing_df.empty:
        sheet.update([df.columns.tolist()] + df.values.tolist())
        return

    # Ensure lead key exists
    if lead_key not in df.columns:
        raise KeyError(f"Lead key '{lead_key}' not found in dataframe")

    existing_df.set_index(lead_key, inplace=True)
    df.set_index(lead_key, inplace=True)

    for key, row in df.iterrows():
        if key in existing_df.index:
            row_idx = existing_df.index.get_loc(key) + 2
            for col, val in row.items():
                if col not in existing_df.columns:
                    continue
                col_idx = existing_df.columns.get_loc(col) + 1
                sheet.update_cell(row_idx, col_idx, val)
        else:
            sheet.append_row([row.get(col, "") for col in existing_df.columns])

# ---------------------------
# ATOMIC PICK (LOCK SAFE)
# ---------------------------
def atomic_pick(sheet, phone, rep_name):
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    if df.empty:
        return False, "No leads available"

    match = df[df["phone"] == phone]
    if match.empty:
        return False, "Lead not found"

    row_idx = match.index[0] + 2

    if match.iloc[0].get("picked") is True:
        return False, f"Already picked by {match.iloc[0].get('picked_by')}"

    headers = sheet.row_values(1)
    picked_col = headers.index("picked") + 1
    picked_by_col = headers.index("picked_by") + 1
    picked_at_col = headers.index("picked_at") + 1

    sheet.update_cell(row_idx, picked_col, True)
    sheet.update_cell(row_idx, picked_by_col, rep_name)
    sheet.update_cell(row_idx, picked_at_col, datetime.utcnow().isoformat())

    return True, "Picked"