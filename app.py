import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from scoring import score_leads
from sheets import load_leads, upsert_leads, atomic_pick

# -----------------------
# CONFIG
# -----------------------
WORKSHEET_NAME = "leads_master"
SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"

ADMIN_PASSWORD = st.secrets["auth"]["admin_password"]
REP_PASSWORDS = st.secrets["auth"]["reps"]

# -----------------------
# SESSION
# -----------------------
if "rep_name" not in st.session_state:
    st.session_state.rep_name = None

if "admin_ok" not in st.session_state:
    st.session_state.admin_ok = False

# -----------------------
# GOOGLE SHEET
# -----------------------
@st.cache_resource
def get_sheet():
    from google.oauth2.service_account import Credentials
    import gspread

    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )

    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

sheet = get_sheet()

# -----------------------
# SLA
# -----------------------
def compute_sla(df):
    if "last_refresh" not in df.columns:
        df["lead_age_days"] = ""
        df["sla_status"] = ""
        return df

    now = datetime.now(timezone.utc)

    def age_days(ts):
        try:
            return (now - datetime.fromisoformat(ts)).days
        except:
            return ""

    df["lead_age_days"] = df["last_refresh"].apply(age_days)

    def sla(row):
        if row.get("intent_band") == "High":
            return "🔴 Urgent" if row.get("lead_age_days", 0) >= 7 else "🟢 Within SLA"
        return ""

    df["sla_status"] = df.apply(sla, axis=1)
    return df

# -----------------------
# UI
# -----------------------
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["📊 Dashboard", "🧑‍💼 Rep Drawer", "🔐 Admin"])

# =======================
# DASHBOARD
# =======================
with tabs[0]:
    df = load_leads(sheet)
    if df.empty:
        st.info("No leads available.")
    else:
        df = compute_sla(df)
        st.dataframe(df, use_container_width=True)

# =======================
# REP DRAWER
# =======================
with tabs[1]:
    if not st.session_state.rep_name:
        name = st.selectbox("Your Name", list(REP_PASSWORDS.keys()))
        pwd = st.text_input("Password", type="password")

        if st.button("Start Session"):
            if REP_PASSWORDS.get(name) == pwd:
                st.session_state.rep_name = name
                st.success(f"Logged in as {name}")
            else:
                st.error("Invalid password")
    else:
        st.success(f"Logged in as {st.session_state.rep_name}")

        df = load_leads(sheet)
        df = compute_sla(df)

        available = df[(df["picked"] != True) | (df["picked"].isna())]

        if available.empty:
            st.info("No leads available.")
        else:
            for idx, row in available.iterrows():
                phone = str(row.get("phone", "")).strip()

                with st.expander(
                    f"{phone} | {row.get('intent_band')} | {row.get('sla_status')}"
                ):
                    st.write(f"Intent Score: {row.get('intent_score')}")
                    st.write(f"Lead State: {row.get('lead_state')}")
                    st.write(f"Age (days): {row.get('lead_age_days')}")

                    # ✅ ABSOLUTELY UNIQUE KEY
                    button_key = f"pick_{idx}_{phone}"

                    if st.button("Pick Lead", key=button_key):
                        success, msg = atomic_pick(
                            sheet=sheet,
                            phone=phone,
                            rep_name=st.session_state.rep_name
                        )

                        if success:
                            st.success("Lead picked successfully")
                            st.rerun()
                        else:
                            st.error(msg)

# =======================
# ADMIN
# =======================
with tabs[2]:
    if not st.session_state.admin_ok:
        admin_pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock Admin"):
            if admin_pwd == ADMIN_PASSWORD:
                st.session_state.admin_ok = True
                st.success("Admin unlocked")
            else:
                st.error("Wrong password")
    else:
        uploaded = st.file_uploader("Upload Refrens CSV", type=["csv"])
        if uploaded:
            df = pd.read_csv(uploaded)
            st.dataframe(df.head())

            if st.button("Run Scoring + Update"):
                scored = score_leads(df)
                scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
                upsert_leads(sheet, scored, lead_key="phone")
                st.success("Sheet updated successfully")