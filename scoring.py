import pandas as pd

CORE_CITIES = ["Mumbai", "Surat", "Indore", "Pune"]

def score_leads(df: pd.DataFrame) -> pd.DataFrame:
    # -----------------------------
    # Normalize columns
    # -----------------------------
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    def present(x):
        return pd.notna(x) and str(x).strip() != ""

    # -----------------------------
    # Field resolvers
    # -----------------------------
    def get_city(row):
        for field in [
            "Customer City",
            "which_city",
            "which_city_would_you_prefer_for_treatment_",
            "kindly_choose_the_city_where_you_wish_to_avail_the_treatment",
            "which_location_do_you_prefer_for_the_treatment?",
        ]:
            if present(row.get(field)):
                return str(row.get(field)).strip()
        return None

    def get_reason(row):
        return row.get("what_is_the_main_reason_you're_considering_lasik_surgery?")

    def get_timeline(row):
        return row.get("when_would_you_prefer_to_undergo_the_lasik_treatment?")

    # -----------------------------
    # Minimum data gate
    # -----------------------------
    def has_minimum_data(row):
        values = [
            get_reason(row),
            get_timeline(row),
            row.get("Call Outcome"),
            row.get("Objection Type"),
            row.get("Consultation Status"),
        ]
        return sum(present(v) for v in values) >= 3

    # -----------------------------
    # Scoring helpers
    # -----------------------------
    def medical_score(reason):
        if not present(reason): return 0
        r = str(reason).lower()
        if "power" in r: return 40
        if "medical" in r: return 35
        if "lifestyle" in r: return 25
        if "cosmetic" in r: return 15
        if "explor" in r: return 5
        return 0

    def timeline_score(t):
        if not present(t): return 0
        t = str(t).lower()
        if "15" in t or "7" in t: return 20
        if "30" in t: return 16
        if "1" in t and "3" in t: return 10
        if "3" in t and "6" in t: return 5
        if "not" in t: return 2
        return 0

    def location_score(city):
        if not present(city): return 0
        return 10 if city in CORE_CITIES else 6

    def finance_score(row):
        insurance = str(row.get("do_you_have_medical_insurance_", "")).lower()
        return 5 if "yes" in insurance else 2

    def call_outcome_score(outcome):
        if not present(outcome): return 0
        o = str(outcome).lower()
        if o == "positive": return 10
        if o == "neutral": return 6
        if o == "no response": return 3
        return 0

    def consultation_score(status):
        if not present(status): return 0
        s = str(status).lower()
        if s == "done": return 15
        if s == "scheduled": return 12
        if "declined" in s: return 6
        if s == "not offered": return 2
        return 0

    # -----------------------------
    # Main loop
    # -----------------------------
    intent_scores, intent_bands, lead_states = [], [], []

    for _, row in df.iterrows():

        if not has_minimum_data(row):
            intent_scores.append("")
            intent_bands.append("Insufficient Data")
            lead_states.append("Open")
            continue

        city = get_city(row)

        score = (
            medical_score(get_reason(row))
            + timeline_score(get_timeline(row))
            + location_score(city)
            + finance_score(row)
            + call_outcome_score(row.get("Call Outcome"))
            + consultation_score(row.get("Consultation Status"))
        )

        intent_scores.append(score)

        if score >= 70:
            band = "High"
        elif score >= 40:
            band = "Medium"
        else:
            band = "Low"

        intent_bands.append(band)

        crm_status = str(row.get("Status", "")).lower()
        objection = str(row.get("Objection Type", "")).lower()
        consultation = str(row.get("Consultation Status", "")).lower()

        if crm_status == "lost":
            if band in ["High", "Medium"] and consultation != "done" and "not interested" not in objection:
                lead_states.append("Lost – Recoverable")
            else:
                lead_states.append("Lost")
        else:
            if band == "High" and consultation != "done":
                lead_states.append("High Intent")
            else:
                lead_states.append("Follow-up")

    df["intent_score"] = intent_scores
    df["intent_band"] = intent_bands
    df["lead_state"] = lead_states

    return df