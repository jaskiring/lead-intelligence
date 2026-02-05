import pandas as pd
from scoring import score_leads
from sheets import connect_sheet, upsert_leads

WORKSHEET_NAME = "leads_master"

print("🚀 Pipeline started")

# 1. Load test CSV
df = pd.read_csv("test_upload.csv")
print(f"📄 CSV loaded: {len(df)} rows")

# 2. Score leads
scored_df = score_leads(df)
print("🧠 Scoring complete")

# 3. Connect to Google Sheet
sheet = connect_sheet("service_account.json", WORKSHEET_NAME)
print("🔗 Connected to Google Sheet")

# 4. Upsert into sheet
upsert_leads(sheet, scored_df, lead_key="phone")
print("✅ Pipeline finished: Sheet updated")