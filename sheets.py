import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# 🔐 PUT YOUR SPREADSHEET ID HERE
SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"

def connect_sheet(json_path, worksheet_name):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_file(
        json_path,
        scopes=scopes
    )

    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(worksheet_name)
    return sheet


def load_leads(sheet):
    records = sheet.get_all_records()
    return pd.DataFrame(records)


def upsert_leads(sheet, df, lead_key="phone"):
    existing = sheet.get_all_records()
    existing_df = pd.DataFrame(existing)

    if existing_df.empty:
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
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