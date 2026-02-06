import pandas as pd
from datetime import datetime, timezone


def load_leads(sheet):
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map external CSV headers to internal canonical schema
    """
    column_map = {
        "Phone": "phone",
        "phone_number": "phone",
        "Contact Name": "name",
        "Contact": "name",
    }

    for src, dst in column_map.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]

    return df


def upsert_leads(sheet, df: pd.DataFrame, lead_key="phone"):
    df = normalize_columns(df)

    if lead_key not in df.columns:
        raise ValueError(f"Missing required key column: {lead_key}")

    existing = sheet.get_all_records()
    existing_df = pd.DataFrame(existing)

    # First write (empty sheet)
    if existing_df.empty:
        sheet.update(
            [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
        )
        return

    existing_df = normalize_columns(existing_df)

    existing_df.set_index(lead_key, inplace=True)
    df.set_index(lead_key, inplace=True)

    for key, row in df.iterrows():
        if key in existing_df.index:
            row_idx = existing_df.index.get_loc(key) + 2
            for col, val in row.items():
                if col not in existing_df.columns:
                    continue
                col_idx = existing_df.columns.get_loc(col) + 1
                sheet.update_cell(row_idx, col_idx, str(val))
        else:
            sheet.append_row(
                [row.get(col, "") for col in existing_df.columns]
            )


def atomic_pick(sheet, phone: str, rep_name: str):
    records = sheet.get_all_records()
    df = pd.DataFrame(records)

    df = normalize_columns(df)

    if "picked" not in df.columns:
        df["picked"] = ""
        df["picked_by"] = ""
        df["picked_at"] = ""

    if phone not in df["phone"].astype(str).values:
        return False, "Lead not found"

    row_idx = df.index[df["phone"].astype(str) == str(phone)][0] + 2

    if str(df.loc[row_idx - 2, "picked"]).lower() == "true":
        return False, "Lead already picked"

    sheet.update_cell(row_idx, df.columns.get_loc("picked") + 1, "TRUE")
    sheet.update_cell(row_idx, df.columns.get_loc("picked_by") + 1, rep_name)
    sheet.update_cell(
        row_idx,
        df.columns.get_loc("picked_at") + 1,
        datetime.now(timezone.utc).isoformat(),
    )

    return True, "Picked"