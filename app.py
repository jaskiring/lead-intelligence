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
            "https://www.googleapis.com/auth/drive",
        ],
    )

    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)


sheet = get_sheet()

# -----------------------
# SESSION
# -----------------------
st.session_state.setdefault("rep_name", None)
st.session_state.setdefault("admin_ok", False)

# -----------------------
# UI
# -----------------------
st.set_page_config("Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["📊 Dashboard", "🧑‍💼 Rep Drawer", "🔐 Admin"])

# =======================
# DASHBOARD
# =======================
with tabs[0]:
    df = load_leads(sheet)
    if df.empty:
        st.info("No leads yet.")
    else:
        st.dataframe(df, use_container_width=True)

# =======================
# REP DRAWER
# =======================
with tabs[1]:
    if not st.session_state.rep_name:
        name = st.selectbox("Your Name", list(REP_PASSWORDS.keys()))
        pwd = st.text_input("Password", type="password")
        if st.button("Start Session"):
            if REP_PASSWORDS[name] == pwd:
                st.session_state.rep_name = name
                st.success(f"Logged in as {name}")
            else:
                st.error("Invalid password")
    else:
        st.success(f"Logged in as {st.session_state.rep_name}")

        df = load_leads(sheet)

        if df.empty:
            st.info("No leads available.")
        else:
            df["picked"] = df.get("picked", "").astype(str)

            cols = st.columns(3)

            for i, row in df.iterrows():
                with cols[i % 3]:
                    st.markdown(
                        f"""
                        <div style="padding:15px;border-radius:12px;background:#0f172a">
                        <b>📱 {row.get("phone","-")}</b><br>
                        🎯 Intent: {row.get("Intent Band","-")}<br>
                        🕒 Timeline: {row.get("when_would_you_prefer_to_undergo_the_lasik_treatment?","-")}<br>
                        🏙 City: {row.get("which_city_would_you_prefer_for_treatment_","-")}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if str(row.get("picked")).lower() == "true":
                        st.error(f"🔒 Picked by {row.get('picked_by')}")
                    else:
                        if st.button(
                            "✅ Pick Lead",
                            key=f"pick_{row.get('phone')}",
                        ):
                            ok, msg = atomic_pick(
                                sheet,
                                phone=row.get("phone"),
                                rep_name=st.session_state.rep_name,
                            )
                            if ok:
                                st.success("Picked")
                                st.rerun()
                            else:
                                st.error(msg)

# =======================
# ADMIN
# =======================
with tabs[2]:
    if not st.session_state.admin_ok:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_ok = True
                st.success("Admin unlocked")
            else:
                st.error("Wrong password")
    else:
        file = st.file_uploader("Upload Refrens CSV", type=["csv"])
        if file:
            df = pd.read_csv(file)
            st.dataframe(df.head())

            if st.button("Run Scoring + Update"):
                df = score_leads(df)
                df["last_refresh"] = datetime.now(timezone.utc).isoformat()
                upsert_leads(sheet, df, lead_key="phone")
                st.success("Sheet updated")