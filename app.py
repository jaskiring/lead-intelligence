import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from scoring import score_leads
from sheets import (
    normalize_refrens_csv,
    load_leads,
    upsert_leads,
    atomic_pick,
)

# ---------------- CONFIG
WORKSHEET_NAME = "leads_master"
SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"

ADMIN_PASSWORD = st.secrets["auth"]["admin_password"]
REP_PASSWORDS = st.secrets["auth"]["reps"]

# ---------------- GOOGLE SHEET
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

# ---------------- SESSION
st.session_state.setdefault("rep", None)
st.session_state.setdefault("admin", False)

# ---------------- UI
st.set_page_config("Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["📊 Dashboard", "🧑‍💼 Rep Drawer", "♻️ Recoverable Leads", "🔐 Admin"])

# ======================================================
# DASHBOARD
# ======================================================
with tabs[0]:
    df = load_leads(sheet)
    st.dataframe(df, use_container_width=True)

# ======================================================
# REP DRAWER (ALL LEADS, PICKABLE)
# ======================================================
with tabs[1]:
    if not st.session_state.rep:
        name = st.selectbox("Your Name", list(REP_PASSWORDS.keys()))
        pwd = st.text_input("Password", type="password")

        if st.button("Login"):
            if REP_PASSWORDS.get(name) == pwd:
                st.session_state.rep = name
                st.rerun()
            else:
                st.error("Invalid password")
    else:
        st.success(f"Logged in as {st.session_state.rep}")
        df = load_leads(sheet)

        cols = st.columns(3)
        for i, row in df.iterrows():
            with cols[i % 3]:
                phone = row["phone"]
                picked = str(row.get("picked", "")).lower() == "true"

                st.markdown(f"### 📞 {phone}")
                st.markdown(f"🔥 {row.get('intent_band')} ({row.get('intent_score')})")
                st.markdown(f"🕒 {row.get('timeline')}")
                st.markdown(f"🏙 {row.get('city')}")
                st.markdown(f"❗ {row.get('objection_type')}")
                st.markdown(f"📞 {row.get('call_outcome')}")
                st.markdown(f"🩺 {row.get('consultation_status')}")
                st.markdown(f"📌 {row.get('lead_state')}")

                st.divider()

                if picked:
                    st.error(f"🔒 Picked by {row.get('picked_by')}")
                else:
                    if st.button("✅ Pick Lead", key=f"pick_rep_{phone}"):
                        ok, msg = atomic_pick(sheet, phone, st.session_state.rep)
                        if ok:
                            st.rerun()
                        else:
                            st.error(msg)

# ======================================================
# RECOVERABLE LEADS (NOW PICKABLE ✅)
# ======================================================
with tabs[2]:
    if not st.session_state.rep:
        st.info("Login as a rep to act on recoverable leads.")
    else:
        df = load_leads(sheet)

        recoverable = df[
            (df["lead_state"].str.contains("Lost", na=False))
            & (df["intent_band"].isin(["High", "Medium"]))
        ]

        if recoverable.empty:
            st.info("No recoverable leads.")
        else:
            cols = st.columns(3)

            for i, row in recoverable.iterrows():
                with cols[i % 3]:
                    phone = row["phone"]
                    picked = str(row.get("picked", "")).lower() == "true"

                    st.markdown(f"### 📞 {phone}")
                    st.markdown(f"🔥 {row.get('intent_band')} ({row.get('intent_score')})")
                    st.markdown(f"🕒 {row.get('timeline')}")
                    st.markdown(f"❗ {row.get('objection_type')}")
                    st.markdown(f"📌 {row.get('lead_state')}")

                    st.markdown(
                        f"🧠 Retry angle: **{row.get('objection_type', '')} strategy**"
                    )

                    st.divider()

                    if picked:
                        st.error(f"🔒 Picked by {row.get('picked_by')}")
                    else:
                        if st.button(
                            "♻️ Pick Recoverable Lead",
                            key=f"pick_recover_{phone}",
                        ):
                            ok, msg = atomic_pick(sheet, phone, st.session_state.rep)
                            if ok:
                                st.rerun()
                            else:
                                st.error(msg)

# ======================================================
# ADMIN
# ======================================================
with tabs[3]:
    if not st.session_state.admin:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock Admin"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin = True
                st.success("Admin unlocked")
    else:
        file = st.file_uploader("Upload Refrens CSV", type="csv")
        if file:
            raw = pd.read_csv(file)
            st.dataframe(raw.head())

            if st.button("Run Scoring + Update"):
                clean = normalize_refrens_csv(raw)
                scored = score_leads(clean)
                scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
                upsert_leads(sheet, scored)
                st.success("Sheet updated correctly")