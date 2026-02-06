import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from scoring import score_leads
from sheets import load_leads, upsert_leads, atomic_pick

# ---------------- CONFIG ----------------
WORKSHEET_NAME = "leads_master"
SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"

ADMIN_PASSWORD = st.secrets["auth"]["admin_password"]
REP_PASSWORDS = st.secrets["auth"]["reps"]

# ---------------- SESSION ----------------
if "rep_name" not in st.session_state:
    st.session_state.rep_name = None
if "admin_ok" not in st.session_state:
    st.session_state.admin_ok = False

# ---------------- SHEET ----------------
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
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

sheet = get_sheet()

# ---------------- SLA ----------------
def compute_sla(df):
    if "last_refresh" not in df.columns:
        return df

    now = datetime.now(timezone.utc)

    def age_days(ts):
        try:
            return (now - datetime.fromisoformat(ts)).days
        except:
            return ""

    df["lead_age_days"] = df["last_refresh"].apply(age_days)
    df["sla_status"] = df.apply(
        lambda r: "🔴 Urgent"
        if r.get("intent_band") == "High" and r.get("lead_age_days", 0) >= 7
        else "🟢 Within SLA",
        axis=1,
    )
    return df

# ---------------- UI ----------------
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["📊 Dashboard", "🧑‍💼 Rep Drawer", "🔐 Admin"])

# ================= DASHBOARD =================
with tabs[0]:
    df = load_leads(sheet)
    if df.empty:
        st.info("No leads available.")
    else:
        df = compute_sla(df)
        st.dataframe(df, use_container_width=True)

# ================= REP DRAWER =================
with tabs[1]:
    if not st.session_state.rep_name:
        name = st.selectbox("Your Name", list(REP_PASSWORDS.keys()))
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if REP_PASSWORDS.get(name) == pwd:
                st.session_state.rep_name = name
                st.rerun()
            else:
                st.error("Invalid credentials")
    else:
        st.success(f"Logged in as {st.session_state.rep_name}")

        df = compute_sla(load_leads(sheet))
        available = df.copy()

        cols = st.columns(3)
        for idx, row in available.iterrows():
            col = cols[idx % 3]
            with col:
                st.markdown(
                    f"""
                    <div style="background:#111827;padding:16px;border-radius:12px;border:1px solid #1f2937">
                        <h4>📱 {row.get('phone')}</h4>
                        <p><b>Intent:</b> {row.get('intent_band')} ({row.get('intent_score')})</p>
                        <p><b>Timeline:</b> {row.get("when_would_you_prefer_to_undergo_the_lasik_treatment?")}</p>
                        <p><b>Reason:</b> {row.get("what_is_the_main_reason_you're_considering_lasik_surgery?")}</p>
                        <p><b>City:</b> {row.get("which_city_would_you_prefer_for_treatment_")}</p>
                        <p><b>SLA:</b> {row.get("sla_status")}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if row.get("picked") is True:
                    st.error(f"🔒 Picked by {row.get('picked_by')}")
                else:
                    if st.button(
                        "✅ Pick Lead",
                        key=f"pick_{row.get('phone')}",
                    ):
                        success, msg = atomic_pick(
                            sheet,
                            phone=str(row.get("phone")),
                            rep_name=st.session_state.rep_name,
                        )
                        if success:
                            st.success("Lead picked")
                            st.rerun()
                        else:
                            st.error(msg)

# ================= ADMIN =================
with tabs[2]:
    if not st.session_state.admin_ok:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_ok = True
                st.rerun()
            else:
                st.error("Wrong password")
    else:
        uploaded = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded:
            df = pd.read_csv(uploaded)
            st.dataframe(df.head())
            if st.button("Run Scoring + Update"):
                scored = score_leads(df)
                scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
                upsert_leads(sheet, scored, lead_key="phone")
                st.success("Sheet updated")