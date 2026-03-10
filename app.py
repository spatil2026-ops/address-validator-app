# app.py
import os
import json
import pandas as pd
import streamlit as st
from openai import OpenAI
from typing import Dict

st.set_page_config(page_title="Address Standardizer", layout="wide")
st.title("Address Standardizer (Excel Upload) — OpenAI Only")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("Missing OPENAI_API_KEY (set it in Streamlit Secrets / environment variables).")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

def standardize_with_openai(address_text: str) -> Dict:
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
    # r.output_text should be JSON string per our prompt
    return json.loads(r.output_text)

# UI: file uploader
uploaded = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

if uploaded:
    df = pd.read_excel(uploaded)
    st.write("Preview:", df.head(10))

    address_col = st.selectbox("Which column contains the address text?", options=df.columns)

    run = st.button("Standardize addresses")
    if run:
        total = len(df)
        if total == 0:
            st.warning("Uploaded file has 0 rows.")
        else:
            # UI elements for progress
            progress = st.progress(0)
            status = st.empty()
            results = []

            # Use a spinner for overall activity
            with st.spinner("Processing addresses... this may take a while"):
                for idx, (_, row) in enumerate(df.iterrows(), start=1):
                    status.text(f"Processing row {idx}/{total}...")
                    progress.progress(int((idx - 1) / total * 100))

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
                            # Ensure quality_flags exists
                            result.setdefault("quality_flags", [])
                        except Exception as e:
                            # capture the error, but continue processing other rows
                            err = f"OpenAI error: {e}"
                            result = {
                                "address1": "", "address2": "", "city": "", "state": "",
                                "zip": "", "zip4": "", "country": "US",
                                "standardized_full": "", "quality_flags": ["OPENAI_ERROR"]
                            }

                    out = dict(row)  # original columns retained
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
                    results.append(out)

            # finalize progress UI
            progress.progress(100)
            status.text("Processing complete.")

            # Build dataframe and show results
            out_df = pd.DataFrame(results)
            st.success("Done!")
            st.dataframe(out_df.head(50), use_container_width=True)

            # Save and provide download
            output_name = "standardized_addresses.xlsx"
            out_df.to_excel(output_name, index=False)
            with open(output_name, "rb") as f:
                st.download_button("Download output Excel", f, file_name=output_name)
