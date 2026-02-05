from sheets import connect_sheet, load_leads
from config import SHEET_NAME, WORKSHEET_NAME

sheet = connect_sheet(
    "service_account.json",
    SHEET_NAME,
    WORKSHEET_NAME
)

df = load_leads(sheet)
print(df.head())