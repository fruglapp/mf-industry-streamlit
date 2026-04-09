import streamlit as st
import pandas as pd
import requests
import re
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

st.set_page_config(page_title="MF Industry Data", page_icon="📊", layout="wide")

# --- Supabase ---

@st.cache_resource
def get_supabase():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"))

@st.cache_resource
def get_service_client():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

supabase = get_service_client()
svc = supabase  # same client for NL queries


def fetch_all(table, order_col="id", desc=True):
    rows, offset, page = [], 0, 1000
    while True:
        q = supabase.table(table).select("*").order(order_col, desc=desc).range(offset, offset + page - 1)
        result = q.execute()
        rows.extend(result.data)
        if len(result.data) < page:
            break
        offset += page
    return pd.DataFrame(rows)


# --- Schema for NL→SQL ---

SCHEMA = """You are a SQL generator for PostgreSQL with Indian Mutual Fund industry data.
Return ONLY a SELECT query. No explanation, no markdown fences, no semicolons.

Tables:
- scheme_master: scheme_code (PK), scheme_name, amc_name, category, asset_class, fund_manager, latest_nav, nav_date
- scheme_holdings: scheme_code (FK), portfolio_date, security_name, security_type, market_value_cr, pct_to_nav, industry_sector, market_cap_class
- security_master: isin (PK), security_name, sector, market_cap_class, nse_symbol
- amfi_monthly_detailed: report_month, section, "group", category, num_schemes, num_folios, funds_mobilized_cr, redemption_cr, net_flow_cr, aum_cr
- amfi_sip_monthly: report_month, sip_contribution_cr, outstanding_accounts_lakh, new_registrations_lakh, discontinued_lakh
- qaaum_fundwise: period_start, fund_house, aaum_excl_cr, aaum_total_cr
- qaaum_schemewise: period_start, amfi_code, scheme_name, mf_name, aaum_excl_cr, aaum_total_cr
- qaaum_totals: period_start, total_aaum_cr, num_fund_houses
- maaum_classified: report_month, mf_name, category, category_group, dist_channel, geography, retail_cr, corporates_cr, banks_fis_cr, fiis_fpis_cr, hni_cr, total_cr
- maaum_mf_ids: mf_id (PK), mf_name, mf_short
- mf_industry_metrics: metric_name, metric_category, period_date, value, unit
- mf_state_data: state, report_date, dimension, sub_dimension, value_pct
- scheme_asset_bucket: scheme_code (PK), bucket

All monetary values in Crores. Always quote "group". Use LIMIT 500 default."""


def run_nl_query(question):
    """Convert natural language to SQL via Gemini, execute via Supabase."""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        return None, "Gemini API key not configured", ""

    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
        json={
            "contents": [{"parts": [{"text": f"{SCHEMA}\n\nQuestion: {question}"}]}],
            "generationConfig": {"maxOutputTokens": 1024, "temperature": 0},
        },
    )
    if resp.status_code != 200:
        return None, f"Gemini API error: {resp.status_code}", ""

    sql = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
    sql = re.sub(r"^```sql\n?", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\n?```$", "", sql).strip().rstrip(";").strip()

    if not re.match(r"^\s*SELECT", sql, re.IGNORECASE):
        return None, "Only SELECT queries allowed", sql

    result = svc.rpc("exec_readonly", {"query_text": sql}).execute()
    if result.data:
        return pd.DataFrame(result.data), None, sql
    return pd.DataFrame(), None, sql


# --- Sidebar ---

st.sidebar.title("MF Industry")

PAGES = ["Ask Data", "Browse Tables", "Industry Snapshot"]
page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")


# =====================================================================
# PAGE: ASK DATA
# =====================================================================

if page == "Ask Data":
    st.header("Ask Data")
    st.caption("Query mutual fund industry data in plain English")

    PRESETS = [
        "Top 10 fund houses by AUM",
        "SIP contribution trend last 12 months",
        "Equity net flows by category last 6 months",
        "Which schemes hold Reliance Industries?",
        "Small cap funds with AUM above 5000 Cr",
        "Top 20 stocks held by most MF schemes",
        "HDFC vs ICICI market share by quarter",
        "Retail vs HNI vs Corporate AUM for HDFC MF",
        "Net flow by asset class for latest month",
        "Fund managers managing more than 3 schemes",
        "Which AMCs have the most schemes?",
        "Debt fund AUM trend last 4 quarters",
    ]

    # Preset grid
    cols = st.columns(3)
    for i, p in enumerate(PRESETS):
        with cols[i % 3]:
            if st.button(p, key=f"p_{i}", use_container_width=True):
                st.session_state["ask_q"] = p

    st.divider()

    # Chat input
    question = st.chat_input("Ask anything about mutual fund industry data...")
    if "ask_q" in st.session_state:
        question = st.session_state.pop("ask_q")

    # Show history
    if "ask_history" not in st.session_state:
        st.session_state["ask_history"] = []

    for item in st.session_state["ask_history"]:
        st.chat_message("user").write(item["question"])
        with st.chat_message("assistant"):
            if item.get("error"):
                st.error(item["error"])
            if item.get("sql"):
                with st.expander("SQL", expanded=False):
                    st.code(item["sql"], language="sql")
            if item.get("df") is not None and len(item["df"]) > 0:
                st.dataframe(item["df"], use_container_width=True, hide_index=True)
                st.caption(f"{len(item['df'])} rows")

    # Process new question
    if question:
        st.chat_message("user").write(question)
        with st.chat_message("assistant"):
            with st.spinner("Querying..."):
                df, error, sql = run_nl_query(question)

            if error:
                st.error(error)
            if sql:
                with st.expander("SQL", expanded=False):
                    st.code(sql, language="sql")
            if df is not None and len(df) > 0:
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption(f"{len(df)} rows")
                st.download_button("Download CSV", df.to_csv(index=False), "mf_query.csv", "text/csv")
            elif not error:
                st.info("No results found. Try a different question.")

        st.session_state["ask_history"].append({"question": question, "df": df, "error": error, "sql": sql})


# =====================================================================
# PAGE: BROWSE TABLES
# =====================================================================

elif page == "Browse Tables":
    st.header("Browse Tables")

    TABLES = {
        "Scheme Master": ("scheme_master", "scheme_code"),
        "Scheme Holdings": ("scheme_holdings", "id"),
        "Security Master": ("security_master", "isin"),
        "AMFI Monthly Detailed": ("amfi_monthly_detailed", "report_month"),
        "AMFI SIP Monthly": ("amfi_sip_monthly", "report_month"),
        "QAAUM by Fund House": ("qaaum_fundwise", "period_start"),
        "QAAUM by Scheme": ("qaaum_schemewise", "period_start"),
        "QAAUM Totals": ("qaaum_totals", "period_start"),
        "MAAUM Classified": ("maaum_classified", "report_month"),
        "MAAUM Fund IDs": ("maaum_mf_ids", "mf_id"),
        "Industry Metrics": ("mf_industry_metrics", "period_date"),
        "State Data": ("mf_state_data", "report_date"),
        "Scheme Asset Bucket": ("scheme_asset_bucket", "scheme_code"),
    }

    selected = st.selectbox("Select table", list(TABLES.keys()))
    table_name, order_col = TABLES[selected]

    with st.spinner(f"Loading {selected}..."):
        df = fetch_all(table_name, order_col)

    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(df)} rows")
    st.download_button("Download CSV", df.to_csv(index=False), f"{table_name}.csv", "text/csv")


# =====================================================================
# PAGE: INDUSTRY SNAPSHOT
# =====================================================================

elif page == "Industry Snapshot":
    st.header("Industry Snapshot")

    # Latest QAAUM totals
    totals = supabase.table("qaaum_totals").select("*").order("period_start", desc=True).limit(4).execute()
    if totals.data:
        tdf = pd.DataFrame(totals.data)
        latest = tdf.iloc[0]
        prev = tdf.iloc[1] if len(tdf) > 1 else None

        c1, c2, c3 = st.columns(3)
        aum = float(latest["total_aaum_cr"])
        c1.metric("Total Industry AAUM", f"₹{aum/100000:.1f}L Cr",
                   delta=f"{((aum / float(prev['total_aaum_cr'])) - 1) * 100:.1f}% QoQ" if prev is not None else None)
        c2.metric("Fund Houses", int(latest["num_fund_houses"]))
        c3.metric("Period", latest["period_name"])

    # Latest SIP
    sip = supabase.table("amfi_sip_monthly").select("*").order("report_month", desc=True).limit(1).execute()
    if sip.data:
        s = sip.data[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("SIP Contribution", f"₹{float(s['sip_contribution_cr']):,.0f} Cr")
        if s.get("outstanding_accounts_lakh"):
            c2.metric("SIP Accounts", f"{float(s['outstanding_accounts_lakh']):.0f} Lakh")
        if s.get("new_registrations_lakh"):
            c3.metric("New SIP Registrations", f"{float(s['new_registrations_lakh']):.1f} Lakh")

    st.divider()

    # Top 10 AMCs
    st.subheader("Top 10 AMCs by AUM")
    qdf = pd.DataFrame(
        supabase.table("qaaum_fundwise").select("fund_house,aaum_total_cr,period_start")
        .order("period_start", desc=True).limit(1000).execute().data
    )
    if not qdf.empty:
        latest_period = qdf["period_start"].max()
        top10 = qdf[qdf["period_start"] == latest_period].nlargest(10, "aaum_total_cr")[["fund_house", "aaum_total_cr"]].copy()
        top10["aaum_total_cr"] = top10["aaum_total_cr"].astype(float)
        top10.columns = ["Fund House", "AAUM (Cr)"]
        top10 = top10.reset_index(drop=True)
        top10.index = top10.index + 1

        col1, col2 = st.columns([1, 1])
        with col1:
            st.dataframe(top10.style.format({"AAUM (Cr)": "{:,.0f}"}), use_container_width=True)
        with col2:
            st.bar_chart(top10.set_index("Fund House")["AAUM (Cr)"], horizontal=True)
