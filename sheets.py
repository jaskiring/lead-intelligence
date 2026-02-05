import pandas as pd
from datetime import datetime, timezone
import gspread


# -----------------------
# LOAD ALL LEADS
# -----------------------
def load_leads(sheet):
    records = sheet.get_all_records()
    return pd.DataFrame(records)


# -----------------------
# UPSERT (ADMIN / PIPELINE)
# -----------------------
def upsert_leads(sheet, df, lead_key="phone"):
    existing = sheet.get_all_records()
    existing_df = pd.DataFrame(existing)

    # Empty sheet → write header + all rows
    if existing_df.empty:
        sheet.update([df.columns.tolist()] + df.fillna("").values.tolist())
        return

    existing_df.set_index(lead_key, inplace=True)
    df = df.copy()
    df.set_index(lead_key, inplace=True)

    for key, row in df.iterrows():
        if key in existing_df.index:
            row_idx = existing_df.index.get_loc(key) + 2
            for col, val in row.items():
                col_idx = existing_df.columns.get_loc(col) + 2
                sheet.update_cell(row_idx, col_idx, val)
        else:
            sheet.append_row([row.get(col, "") for col in existing_df.columns])


# -----------------------
# ATOMIC PICK (REP SAFE)
# -----------------------
def atomic_pick(sheet, phone, rep_name):
    """
    Prevents two reps from picking the same lead.
    """
    records = sheet.get_all_records()

    for i, row in enumerate(records):
        if str(row.get("phone")) == str(phone):
            if row.get("picked") is True:
                return False, f"Already picked by {row.get('picked_by')}"

            row_idx = i + 2  # Google Sheets row index
            now = datetime.now(timezone.utc).isoformat()

            sheet.update_cell(row_idx, sheet.find("picked").col, True)
            sheet.update_cell(row_idx, sheet.find("picked_by").col, rep_name)
            sheet.update_cell(row_idx, sheet.find("picked_at").col, now)

            return True, "Lead locked successfully"

    return False, "Lead not found"