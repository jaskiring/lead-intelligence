import pandas as pd

CORE_CITIES = ["Mumbai", "Surat", "Indore", "Pune"]

def score_leads(df: pd.DataFrame) -> pd.DataFrame:
    def present(x):
        return pd.notna(x) and str(x).strip() != ""

    def medical_score(reason):
        if not present(reason):
            return 0
        r = str(reason).lower()
        if "power" in r:
            return 40
        if "medical" in r:
            return 35
        if "lifestyle" in r:
            return 25
        if "cosmetic" in r:
            return 15
        if "explor" in r:
            return 5
        return 0

    def timeline_score(t):
        if not present(t):
            return 0
        t = str(t).lower()
        if "15" in t or "7" in t:
            return 20
        if "30" in t:
            return 16
        if "1" in t and "3" in t:
            return 10
        if "3" in t and "6" in t:
            return 5
        return 0

    def location_score(city):
        if not present(city):
            return 0
        return 10 if city.strip() in CORE_CITIES else 6

    scores = []
    bands = []
    states = []

    for _, row in df.iterrows():
        score = (
            medical_score(row.get("reason"))
            + timeline_score(row.get("timeline"))
            + location_score(row.get("city"))
        )

        scores.append(score)

        if score >= 70:
            band = "High"
            state = "High Intent"
        elif score >= 40:
            band = "Medium"
            state = "Follow-up"
        else:
            band = "Low"
            state = "Follow-up"

        bands.append(band)
        states.append(state)

    df["intent_score"] = scores
    df["intent_band"] = bands
    df["lead_state"] = states

    return df