import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from sheets import normalize_refrens_csv, load_leads, upsert_leads, atomic_pick
from scoring import score_leads

SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"
ADMIN_PASSWORD = st.secrets["auth"]["admin_password"]
REP_PASSWORDS = st.secrets["auth"]["reps"]

@st.cache_resource
def get_sheet():
    from google.oauth2.service_account import Credentials
    import gspread
    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID).worksheet("leads_master")

sheet = get_sheet()

st.session_state.setdefault("rep", None)
st.session_state.setdefault("admin", False)

def compute_sla(df):
    now = datetime.now(timezone.utc)
    def sla(row):
        try:
            days = (now - datetime.fromisoformat(row["last_refresh"])).days
        except:
            return ""
        return "URGENT" if row.get("intent_band") == "High" and days >= 7 else ""
    df["sla_status"] = df.apply(sla, axis=1)
    return df

st.set_page_config("Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["🧑‍💼 Rep Drawer", "📁 My Leads", "♻️ Recoverable", "🔐 Admin"])

# Rep Drawer
with tabs[0]:
    if not st.session_state.rep:
        name = st.selectbox("Name", list(REP_PASSWORDS))
        pwd = st.text_input("Password", type="password")
        if st.button("Login") and REP_PASSWORDS[name] == pwd:
            st.session_state.rep = name
            st.rerun()
    else:
        df = compute_sla(load_leads(sheet))
        for i in range(0, len(df), 3):
            cols = st.columns(3)
            for col, (_, row) in zip(cols, df.iloc[i:i+3].iterrows()):
                with col:
                    st.write(row["phone"])
                    if row.get("picked") == "TRUE":
                        st.error(f"Picked by {row.get('picked_by')}")
                    else:
                        if st.button("Pick", key=row["phone"]):
                            ok, msg = atomic_pick(sheet, row["phone"], st.session_state.rep)
                            if ok: st.rerun()

# My Leads
with tabs[1]:
    if st.session_state.rep:
        df = compute_sla(load_leads(sheet))
        mine = df[df["picked_by"] == st.session_state.rep]
        st.dataframe(mine)

# Recoverable
with tabs[2]:
    df = compute_sla(load_leads(sheet))
    recoverable = df[
        (df["status"].str.lower().str.contains("lost")) &
        (df["intent_band"].isin(["High", "Medium"])) &
        (df["consultation_status"].str.lower() != "done")
    ]
    st.dataframe(recoverable)

# Admin
with tabs[3]:
    pwd = st.text_input("Admin Password", type="password")
    if st.button("Unlock") and pwd == ADMIN_PASSWORD:
        st.session_state.admin = True

    if st.session_state.admin:
        file = st.file_uploader("Upload Refrens CSV", type="csv")
        if file:
            raw = pd.read_csv(file)
            clean = normalize_refrens_csv(raw)
            scored = score_leads(clean)
            scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
            upsert_leads(sheet, scored)
            st.success("Updated")