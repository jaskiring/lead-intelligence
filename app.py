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

# ======================================================
# CONFIG
# ======================================================
WORKSHEET_NAME = "leads_master"
SPREADSHEET_ID = "1JjcxzsJpf-s92-w_Mc10K3dL_SewejThMLzj4O-7pbs"

ADMIN_PASSWORD = st.secrets["auth"]["admin_password"]
REP_PASSWORDS = st.secrets["auth"]["reps"]

# ======================================================
# GOOGLE SHEET
# ======================================================
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

# ======================================================
# SESSION
# ======================================================
st.session_state.setdefault("rep", None)
st.session_state.setdefault("admin", False)

# ======================================================
# SLA LOGIC
# ======================================================
def compute_sla(row):
    last_refresh = row.get("last_refresh")
    if not last_refresh:
        return "", "⚪ No SLA"

    try:
        last = datetime.fromisoformat(last_refresh)
        age_days = (datetime.now(timezone.utc) - last).days
    except Exception:
        return "", "⚪ No SLA"

    intent = row.get("intent_band")

    if intent == "High":
        if age_days <= 7:
            return age_days, "🟢 Within SLA"
        elif age_days <= 10:
            return age_days, "🟡 At Risk"
        else:
            return age_days, "🔴 Breached"

    if intent == "Medium":
        if age_days <= 14:
            return age_days, "🟢 Within SLA"
        else:
            return age_days, "🟡 At Risk"

    return age_days, "⚪ No SLA"

# ======================================================
# UI
# ======================================================
st.set_page_config(page_title="Lead Intelligence Portal", layout="wide")
st.title("🧠 Lead Intelligence Portal")

tabs = st.tabs(["📊 Dashboard", "🧑‍💼 Rep Drawer", "🔐 Admin"])

# ======================================================
# DASHBOARD (TABLE)
# ======================================================
with tabs[0]:
    df = load_leads(sheet)
    st.dataframe(df, use_container_width=True)

# ======================================================
# REP DRAWER (TILE VIEW + SLA)
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

        if df.empty:
            st.info("No leads available.")
        else:
            cols = st.columns(3)

            for idx, row in df.iterrows():
                with cols[idx % 3]:

                    phone = row.get("phone", "")
                    picked = str(row.get("picked", "")).lower() == "true"

                    age_days, sla_status = compute_sla(row)

                    # ---------- HEADER
                    st.markdown(
                        f"""
                        ### 📞 {phone}
                        **{row.get("name", "")}**  
                        🏙️ {row.get("city", "")}
                        """
                    )

                    st.divider()

                    # ---------- INTENT
                    st.markdown(
                        f"""
                        🔥 **Intent**: `{row.get("intent_band", "")}`  
                        📊 **Score**: {row.get("intent_score", "")}  
                        🕒 **Timeline**: {row.get("timeline", "")}
                        """
                    )

                    st.divider()

                    # ---------- SLA
                    st.markdown(
                        f"""
                        ⏱ **Lead Age**: {age_days} days  
                        🚦 **SLA**: {sla_status}
                        """
                    )

                    st.divider()

                    # ---------- CONVERSATION
                    st.markdown(
                        f"""
                        📞 **Call Outcome**: {row.get("call_outcome", "")}  
                        ❗ **Objection**: {row.get("objection_type", "")}  
                        🩺 **Consultation**: {row.get("consultation_status", "")}  
                        📌 **Status**: {row.get("status", "")}
                        """
                    )

                    st.divider()

                    # ---------- PICK
                    if picked:
                        st.error(
                            f"""
                            🔒 **Picked**  
                            👤 {row.get("picked_by", "")}  
                            ⏱ {row.get("picked_at", "")}
                            """
                        )
                    else:
                        if st.button(
                            "✅ Pick Lead",
                            key=f"pick_{idx}_{phone}",
                            use_container_width=True,
                        ):
                            ok, msg = atomic_pick(
                                sheet,
                                phone=phone,
                                rep_name=st.session_state.rep,
                            )
                            if ok:
                                st.success("Lead picked")
                                st.rerun()
                            else:
                                st.error(msg)

# ======================================================
# ADMIN
# ======================================================
with tabs[2]:
    if not st.session_state.admin:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Unlock Admin"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin = True
                st.success("Admin unlocked")
            else:
                st.error("Wrong password")
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