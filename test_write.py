import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import traceback

print("🚀 Script started")

try:
    WORKSHEET_NAME = "leads_master"
    SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"

    print("🔑 Loading credentials...")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_file(
        "service_account.json",
        scopes=scopes
    )

    print("🔌 Authorizing client...")
    client = gspread.authorize(creds)

    print("📄 Opening sheet...")
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

    print("✍️ Appending row...")
    sheet.append_row([
        "TEST_PHONE",
        "Test Name",
        "High eye power",
        "Within 15 days",
        "Mumbai",
        "Timing",
        "Positive",
        "Scheduled",
        "Open",
        "",
        "",
        "",
        False,
        "",
        "",
        datetime.now().isoformat()
    ])

    print("✅ Row appended successfully")

except Exception:
    print("❌ ERROR OCCURRED")
    traceback.print_exc()