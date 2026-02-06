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

WORKSHEET_NAME = "leads_master"
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
    return gspread.authorize(creds).open_by_key(
        SPREADSHEET_ID
    ).worksheet(WORKSHEET_NAME)


sheet = get_sheet()

st.session_state.setdefault("rep", None)
st.session_state.setdefault("admin", False)

st.set_page_config("Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["Dashboard", "Rep Drawer", "Admin"])

# ---------------- Dashboard
with tabs[0]:
    df = load_leads(sheet)
    st.dataframe(df, use_container_width=True)

# ---------------- Rep Drawer
with tabs[1]:
    if not st.session_state.rep:
        name = st.selectbox("Name", list(REP_PASSWORDS.keys()))
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if REP_PASSWORDS[name] == pwd:
                st.session_state.rep = name
                st.rerun()
            else:
                st.error("Wrong password")
    else:
        st.success(f"Logged in as {st.session_state.rep}")
        df = load_leads(sheet)

        cols = st.columns(3)
        for i, row in df.iterrows():
            with cols[i % 3]:
                st.markdown(
                    f"""
                    **📞 {row.phone}**  
                    🎯 {row.intent_band}  
                    🕒 {row.timeline}  
                    🏙 {row.city}
                    """
                )
                if str(row.picked).lower() == "true":
                    st.error(f"Picked by {row.picked_by}")
                else:
                    if st.button(
                        "Pick Lead",
                        key=f"pick_{row.phone}",
                    ):
                        ok, msg = atomic_pick(
                            sheet, row.phone, st.session_state.rep
                        )
                        if ok:
                            st.rerun()
                        else:
                            st.error(msg)

# ---------------- Admin
with tabs[2]:
    pwd = st.text_input("Admin Password", type="password")
    if st.button("Unlock"):
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin = True

    if st.session_state.admin:
        file = st.file_uploader("Upload Refrens CSV", type="csv")
        if file:
            raw = pd.read_csv(file)
            clean = normalize_refrens_csv(raw)
            scored = score_leads(clean)
            scored["last_refresh"] = datetime.now(timezone.utc).isoformat()
            upsert_leads(sheet, scored)
            st.success("Sheet updated correctly")