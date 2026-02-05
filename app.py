import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from scoring import score_leads
from sheets import load_leads, upsert_leads, atomic_pick

# -----------------------
# CONFIG
# -----------------------
WORKSHEET_NAME = "leads_master"

ADMIN_PASSWORD = st.secrets["auth"]["admin_password"]
REP_PASSWORDS = st.secrets["auth"]["reps"]

# -----------------------
# SESSION STATE
# -----------------------
if "rep_name" not in st.session_state:
    st.session_state.rep_name = None

if "admin_ok" not in st.session_state:
    st.session_state.admin_ok = False

# -----------------------
# GOOGLE SHEETS CONNECT
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
    sheet = client.open_by_key(
        "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"
    ).worksheet(WORKSHEET_NAME)

    return sheet

sheet = get_sheet()

# -----------------------
# SLA + COLOR HELPERS
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
            return "Urgent" if row["lead_age_days"] >= 7 else "Within SLA"
        return ""

    df["sla_status"] = df.apply(sla, axis=1)
    return df


def row_style(row):
    if row.get("intent_band") == "High":
        return ["background-color: #ffe6e6"] * len(row)
    if row.get("intent_band") == "Medium":
        return ["background-color: #fff5cc"] * len(row)
    if row.get("intent_band") == "Low":
        return ["background-color: #e6ffe6"] * len(row)
    return [""] * len(row)

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
    st.subheader("All Leads")

    df = load_leads(sheet)
    df = compute_sla(df)

    if df.empty:
        st.info("No leads yet.")
    else:
        df = df.sort_values(
            by=["sla_status", "intent_score"],
            ascending=[False, False]
        )

        st.dataframe(
            df.style.apply(row_style, axis=1),
            use_container_width=True
        )

# =======================
# REP DRAWER
# =======================
with tabs[1]:
    st.subheader("Rep Drawer")

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
        available = df[(df["picked"] != True) | (df["picked"].isna())]

        if available.empty:
            st.info("No available leads.")
        else:
            for _, row in available.iterrows():
                with st.expander(f"{row['phone']} | {row.get('intent_band')}"):
                    st.write(f"Intent Score: {row.get('intent_score')}")
                    st.write(f"Lead State: {row.get('lead_state')}")

                    if st.button("Pick Lead", key=f"pick_{row['phone']}"):
                        success, msg = atomic_pick(
                            sheet,
                            phone=row["phone"],
                            rep_name=st.session_state.rep_name
                        )

                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

# =======================
# ADMIN PANEL
# =======================
with tabs[2]:
    st.subheader("Admin Panel")

    if not st.session_state.admin_ok:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock Admin"):
            if pwd == ADMIN_PASSWORD:
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
                st.success("Leads updated successfully")