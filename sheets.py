import gspread
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
import streamlit as st


# -----------------------
# GOOGLE AUTH
# -----------------------
def _get_client():
    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)


# -----------------------
# OPEN SHEET
# -----------------------
def open_sheet(spreadsheet_id: str, worksheet_name: str):
    client = _get_client()
    return client.open_by_key(spreadsheet_id).worksheet(worksheet_name)


# -----------------------
# LOAD LEADS
# -----------------------
def load_leads(sheet):
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


# -----------------------
# UPSERT LEADS
# -----------------------
def upsert_leads(sheet, df: pd.DataFrame, lead_key="phone"):
    existing = sheet.get_all_records()

    if not existing:
        sheet.update([df.columns.tolist()] + df.fillna("").values.tolist())
        return

    existing_df = pd.DataFrame(existing)

    existing_df.set_index(lead_key, inplace=True)
    df = df.copy()
    df.set_index(lead_key, inplace=True)

    for key, row in df.iterrows():
        if key in existing_df.index:
            row_idx = existing_df.index.get_loc(key) + 2
            for col, val in row.items():
                col_idx = existing_df.columns.get_loc(col) + 1
                sheet.update_cell(row_idx, col_idx, "" if pd.isna(val) else val)
        else:
            sheet.append_row(
                [row.get(col, "") for col in existing_df.columns]
            )


# -----------------------
# ATOMIC PICK (LOCK)
# -----------------------
def atomic_pick(sheet, phone: str, rep_name: str):
    rows = sheet.get_all_records()

    for i, row in enumerate(rows):
        if str(row.get("phone")) == str(phone):
            row_idx = i + 2

            if row.get("picked") is True:
                return False, f"Already picked by {row.get('picked_by')}"

            sheet.update_cell(row_idx, sheet.find("picked").col, True)
            sheet.update_cell(row_idx, sheet.find("picked_by").col, rep_name)
            sheet.update_cell(
                row_idx,
                sheet.find("picked_at").col,
                datetime.utcnow().isoformat(),
            )

            return True, "Lead picked successfully"

    return False, "Lead not found"