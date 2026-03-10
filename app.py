import os
import json
import pandas as pd
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Address Standardizer", layout="wide")
st.title("Address Standardizer (Excel Upload) — OpenAI Only")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("Missing OPENAI_API_KEY (set it in Streamlit Secrets / environment variables).")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

def standardize_with_openai(address_text: str) -> dict:
    """
    Returns a JSON object with standardized address fields + flags.
    """
    prompt = f"""
You are an address standardization assistant.

Goal:
- Standardize formatting and split into fields (best-effort).
- Do NOT invent missing information.
- If something is missing/unknown, return empty string for that field.
- Output JSON only.

Return this JSON schema exactly:
{{
  "address1": "",
  "address2": "",
  "city": "",
  "state": "",
  "zip": "",
  "zip4": "",
  "country": "US",
  "standardized_full": "",
  "quality_flags": []
}}

Rules:
- Use USPS-style abbreviations when obvious (e.g., Street->ST, Road->RD, Avenue->AVE).
- Keep apartment/unit/suite in address2 (APT, UNIT, STE, FL, BLDG).
- Uppercase state as 2-letter code if present.
- ZIP should be 5 digits if present. ZIP4 should be 4 digits if present.
- If the address appears non-US, set country accordingly and add a flag "NON_US".

Address:
{address_text}
"""

    r = client.responses.create(
        model="gpt-4o-mini",
        input=prompt,
        text={"format": {"type": "json_object"}},
    )
    return json.loads(r.output_text)

uploaded = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

if uploaded:
    df = pd.read_excel(uploaded)
    st.write("Preview:", df.head(10))

    address_col = st.selectbox("Which column contains the address text?", options=df.columns)

    run = st.button("Standardize addresses")
    if run:
        out_rows = []
        for _, row in df.iterrows():
            raw = str(row.get(address_col, "")).strip()
            result = {}
            err = ""

            if not raw:
                err = "Empty address"
                result = {
                    "address1": "", "address2": "", "city": "", "state": "",
                    "zip": "", "zip4": "", "country": "US",
                    "standardized_full": "", "quality_flags": ["EMPTY_ADDRESS"]
                }
            else:
                try:
                    result = standardize_with_openai(raw)
                    # Defensive defaults
                    result.setdefault("quality_flags", [])
                except Exception as e:
                    err = f"OpenAI error: {e}"
                    result = {
                        "address1": "", "address2": "", "city": "", "state": "",
                        "zip": "", "zip4": "", "country": "US",
                        "standardized_full": "", "quality_flags": ["OPENAI_ERROR"]
                    }

            out = dict(row)
            out.update({
                "standard_address1": result.get("address1", ""),
                "standard_address2": result.get("address2", ""),
                "standard_city": result.get("city", ""),
                "standard_state": result.get("state", ""),
                "standard_zip": result.get("zip", ""),
                "standard_zip4": result.get("zip4", ""),
                "standard_country": result.get("country", "US"),
                "standard_full": result.get("standardized_full", ""),
                "quality_flags": ", ".join(result.get("quality_flags", [])),
                "error_message": err,
            })
            out_rows.append(out)

        out_df = pd.DataFrame(out_rows)
        st.success("Done!")
        st.dataframe(out_df.head(50), use_container_width=True)

        output_name = "standardized_addresses.xlsx"
        out_df.to_excel(output_name, index=False)

        with open(output_name, "rb") as f:
            st.download_button("Download output Excel", f, file_name=output_name)
