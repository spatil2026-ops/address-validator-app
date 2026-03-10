import os
import json
import pandas as pd
import streamlit as st
import requests
from openai import OpenAI

st.set_page_config(page_title="Address Validator", layout="wide")
st.title("Address Validation Tool (Excel Upload)")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
USPS_TOKEN_URL = os.getenv("USPS_TOKEN_URL")          # from USPS portal
USPS_ADDRESSES_URL = os.getenv("USPS_ADDRESSES_URL")  # from USPS portal
USPS_CLIENT_ID = os.getenv("USPS_CLIENT_ID")
USPS_CLIENT_SECRET = os.getenv("USPS_CLIENT_SECRET")

if not OPENAI_API_KEY:
    st.error("Missing OPENAI_API_KEY")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

@st.cache_data(show_spinner=False)
def get_usps_token():
    # USPS uses OAuth2 Client Credentials on the new platform
    resp = requests.post(
        USPS_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(USPS_CLIENT_ID, USPS_CLIENT_SECRET),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def parse_with_openai(address_text: str) -> dict:
    # Model returns JSON. Structured Outputs/JSON mode helps keep it machine-readable.
    prompt = f"""
Return JSON only.

Parse this US mailing address into:
address1, address2, city, state, zip

Address:
{address_text}
"""
    r = client.responses.create(
        model="gpt-4o-mini",
        input=prompt,
        text={"format": {"type": "json_object"}},
    )
    # Responses API returns text; parse JSON
    return json.loads(r.output_text)

def validate_with_usps(token: str, a: dict) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "streetAddress": a.get("address1",""),
        "secondaryAddress": a.get("address2",""),
        "city": a.get("city",""),
        "state": a.get("state",""),
        "ZIPCode": a.get("zip",""),
    }
    resp = requests.post(USPS_ADDRESSES_URL, json=payload, headers=headers, timeout=30)
    # Don’t throw immediately—capture USPS error messages in output
    return {"status_code": resp.status_code, "body": resp.json() if resp.headers.get("content-type","").startswith("application/json") else resp.text}

uploaded = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

if uploaded:
    df = pd.read_excel(uploaded)

    st.write("Preview:", df.head(10))

    # You can change this column name if your Excel uses a different header
    address_col = st.selectbox("Which column contains the full address?", options=df.columns)

    run = st.button("Validate addresses")
    if run:
        token = get_usps_token()
        out_rows = []

        for i, row in df.iterrows():
            raw = str(row.get(address_col, "")).strip()
            parsed = {}
            usps = {}
            err = ""

            if not raw:
                err = "Empty address"
            else:
                try:
                    parsed = parse_with_openai(raw)
                except Exception as e:
                    err = f"OpenAI parse error: {e}"

                if not err:
                    try:
                        usps = validate_with_usps(token, parsed)
                    except Exception as e:
                        err = f"USPS error: {e}"

            out = dict(row)
            out.update({
                "parsed_address1": parsed.get("address1",""),
                "parsed_address2": parsed.get("address2",""),
                "parsed_city": parsed.get("city",""),
                "parsed_state": parsed.get("state",""),
                "parsed_zip": parsed.get("zip",""),
                "usps_status_code": usps.get("status_code",""),
                "usps_response": json.dumps(usps.get("body",""), ensure_ascii=False)[:5000],
                "error_message": err,
            })
            out_rows.append(out)

        out_df = pd.DataFrame(out_rows)
        st.success("Done!")
        st.dataframe(out_df.head(20), use_container_width=True)

        # Download
        output_name = "validated_addresses.xlsx"
        out_df.to_excel(output_name, index=False)
        with open(output_name, "rb") as f:
            st.download_button("Download output Excel", f, file_name=output_name)
