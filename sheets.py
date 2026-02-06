import pandas as pd
from datetime import datetime

# --------------------------------
# NORMALIZE DATAFRAME
# --------------------------------
def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip() for c in df.columns]

    # Map phone variants → phone
    phone_map = [
        "phone",
        "Phone",
        "phone_number",
        "Phone Number",
        "mobile",
        "Mobile",
        "Contact Phone",
    ]

    for col in phone_map:
        if col in df.columns:
            df["phone"] = df[col].astype(str)
            break

    if "phone" not in df.columns:
        raise ValueError("No phone column found in sheet")

    return df

# --------------------------------
# LOAD LEADS
# --------------------------------
def load_leads(sheet):
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    return normalize_df(df)

# --------------------------------
# UPSERT LEADS
# --------------------------------
def upsert_leads(sheet, df, lead_key="phone"):
    df = normalize_df(df)

    existing = sheet.get_all_records()
    if not existing:
        sheet.update([df.columns.tolist()] + df.values.tolist())
        return

    existing_df = normalize_df(pd.DataFrame(existing))

    existing_df.set_index(lead_key, inplace=True)
    df.set_index(lead_key, inplace=True)

    headers = sheet.row_values(1)

    for phone, row in df.iterrows():
        if phone in existing_df.index:
            row_idx = existing_df.index.get_loc(phone) + 2
            for col, val in row.items():
                if col in headers:
                    col_idx = headers.index(col) + 1
                    sheet.update_cell(row_idx, col_idx, val)
        else:
            sheet.append_row([row.get(h, "") for h in headers])

# --------------------------------
# ATOMIC PICK
# --------------------------------
def atomic_pick(sheet, phone, rep_name):
    df = load_leads(sheet)

    match = df[df["phone"] == str(phone)]
    if match.empty:
        return False, "Lead not found"

    row = match.iloc[0]
    row_idx = match.index[0] + 2

    if row.get("picked") is True:
        return False, f"Already picked by {row.get('picked_by')}"

    headers = sheet.row_values(1)

    def col(name):
        return headers.index(name) + 1

    sheet.update_cell(row_idx, col("picked"), True)
    sheet.update_cell(row_idx, col("picked_by"), rep_name)
    sheet.update_cell(row_idx, col("picked_at"), datetime.utcnow().isoformat())

    return True, "Picked"