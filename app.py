import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client
import os

load_dotenv()

st.set_page_config(
    page_title="MF Industry Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


@st.cache_data(ttl=3600)
def load_monthly_data():
    supabase = get_supabase()
    result = (
        supabase.table("amfi_monthly_detailed")
        .select("*")
        .order("report_month", desc=True)
        .execute()
    )
    df = pd.DataFrame(result.data)
    df["report_month"] = pd.to_datetime(df["report_month"])
    for col in ["aum_cr", "net_flow_cr", "funds_mobilized_cr", "redemption_cr"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=3600)
def load_qaaum_data():
    supabase = get_supabase()
    result = (
        supabase.table("qaaum_fundwise")
        .select("*")
        .order("period_start", desc=True)
        .execute()
    )
    df = pd.DataFrame(result.data)
    df["period_start"] = pd.to_datetime(df["period_start"])
    df["aaum_total_cr"] = pd.to_numeric(df["aaum_total_cr"], errors="coerce")
    return df


@st.cache_data(ttl=3600)
def load_industry_metrics():
    supabase = get_supabase()
    result = (
        supabase.table("mf_industry_metrics")
        .select("*")
        .order("period_date", desc=True)
        .execute()
    )
    df = pd.DataFrame(result.data)
    df["period_date"] = pd.to_datetime(df["period_date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def fmt_cr(val):
    """Format crore values as readable lakhs crore / thousands crore."""
    if pd.isna(val):
        return "—"
    if abs(val) >= 100000:
        return f"{val / 100000:,.1f}L Cr"
    if abs(val) >= 1000:
        return f"{val / 1000:,.1f}K Cr"
    return f"{val:,.0f} Cr"


def fmt_num(val):
    """Format large numbers with L/K suffixes."""
    if pd.isna(val):
        return "—"
    if abs(val) >= 10000000:
        return f"{val / 10000000:,.1f} Cr"
    if abs(val) >= 100000:
        return f"{val / 100000:,.1f}L"
    if abs(val) >= 1000:
        return f"{val / 1000:,.1f}K"
    return f"{val:,.0f}"


# --- Sidebar ---
st.sidebar.title("MF Industry")
st.sidebar.caption("Indian Mutual Fund Industry Dashboard")

page = st.sidebar.radio(
    "Navigate",
    ["Pulse", "Flows", "Categories", "QAAUM Rankings", "Data Explorer"],
    label_visibility="collapsed",
)

# --- Load data ---
df = load_monthly_data()
latest_month = df["report_month"].max()
prev_month = latest_month - pd.DateOffset(months=1)
year_ago = latest_month - pd.DateOffset(months=12)

# --- Pages ---

if page == "Pulse":
    st.title("Industry Pulse")
    st.caption(f"Latest data: {latest_month.strftime('%B %Y')}")

    # Grand total row for latest month
    gt = df[(df["report_month"] == latest_month) & (df["category"] == "Grand Total")]
    gt_prev = df[(df["report_month"] == prev_month) & (df["category"] == "Grand Total")]
    gt_yoy = df[(df["report_month"] == year_ago) & (df["category"] == "Grand Total")]

    if not gt.empty:
        row = gt.iloc[0]
        col1, col2, col3, col4 = st.columns(4)

        aum_now = row["aum_cr"]
        aum_prev = gt_prev.iloc[0]["aum_cr"] if not gt_prev.empty else None
        aum_yoy = gt_yoy.iloc[0]["aum_cr"] if not gt_yoy.empty else None

        col1.metric(
            "Total AUM",
            fmt_cr(aum_now),
            delta=f"{((aum_now / aum_prev) - 1) * 100:.1f}% MoM" if aum_prev else None,
        )
        col2.metric(
            "Net Flows",
            fmt_cr(row["net_flow_cr"]),
            delta=f"{fmt_cr(gt_prev.iloc[0]['net_flow_cr'])} prev" if not gt_prev.empty else None,
        )
        col3.metric("Folios", fmt_num(row["num_folios"]))
        col4.metric("Schemes", fmt_num(row["num_schemes"]))

    # AUM trend chart
    st.subheader("AUM Trend")
    aum_trend = (
        df[df["category"] == "Grand Total"]
        .sort_values("report_month")[["report_month", "aum_cr"]]
        .set_index("report_month")
    )
    st.area_chart(aum_trend, y="aum_cr", color="#4ade80", use_container_width=True)

    # Group breakdown
    st.subheader("AUM by Group")
    groups = ["Debt Schemes", "Equity Schemes", "Hybrid Schemes", "Solution Oriented Schemes", "Other Schemes"]
    group_data = df[
        (df["report_month"] == latest_month)
        & (df["category"].isin(groups))
    ][["category", "aum_cr", "net_flow_cr", "num_folios"]].sort_values("aum_cr", ascending=False)
    group_data.columns = ["Group", "AUM (Cr)", "Net Flow (Cr)", "Folios"]
    st.dataframe(group_data, use_container_width=True, hide_index=True)


elif page == "Flows":
    st.title("Flow Tracker")
    st.caption(f"Latest data: {latest_month.strftime('%B %Y')}")

    # Time range selector
    months_available = sorted(df["report_month"].unique(), reverse=True)
    n_months = st.slider("Show last N months", 3, 24, 12)
    cutoff = latest_month - pd.DateOffset(months=n_months)

    groups = ["Debt Schemes", "Equity Schemes", "Hybrid Schemes", "Solution Oriented Schemes", "Other Schemes"]
    flow_df = df[
        (df["report_month"] > cutoff)
        & (df["category"].isin(groups))
    ][["report_month", "category", "net_flow_cr"]].copy()
    flow_df["month"] = flow_df["report_month"].dt.strftime("%Y-%m")

    # Pivot for chart
    pivot = flow_df.pivot_table(index="month", columns="category", values="net_flow_cr", aggfunc="sum").fillna(0)
    pivot = pivot.sort_index()

    st.bar_chart(pivot, use_container_width=True)

    # Net flow summary table
    st.subheader("Net Flows by Group — Latest Month")
    latest_flows = flow_df[flow_df["report_month"] == latest_month][["category", "net_flow_cr"]].sort_values(
        "net_flow_cr", ascending=False
    )
    latest_flows.columns = ["Group", "Net Flow (Cr)"]
    st.dataframe(latest_flows, use_container_width=True, hide_index=True)


elif page == "Categories":
    st.title("Category Deep Dive")
    st.caption(f"Latest data: {latest_month.strftime('%B %Y')}")

    # Group filter
    groups = ["Debt Schemes", "Equity Schemes", "Hybrid Schemes", "Solution Oriented Schemes", "Other Schemes"]
    selected_group = st.selectbox("Select Group", groups)

    # Map group name to the group column value
    group_map = {
        "Debt Schemes": "Debt Schemes",
        "Equity Schemes": "Equity Schemes",
        "Hybrid Schemes": "Hybrid Schemes",
        "Solution Oriented Schemes": "Solution Oriented Schemes",
        "Other Schemes": "Other Schemes",
    }

    # Get categories within this group (exclude the group total row)
    cat_df = df[
        (df["report_month"] == latest_month)
        & (df["group"] == group_map[selected_group])
        & (~df["category"].isin(groups + ["Grand Total"]))
        & (df["section"] == "Open Ended Schemes")
    ][["category", "aum_cr", "net_flow_cr", "num_folios", "num_schemes"]].sort_values("aum_cr", ascending=False)

    if cat_df.empty:
        st.info("No sub-category data available for this group.")
    else:
        cat_df.columns = ["Category", "AUM (Cr)", "Net Flow (Cr)", "Folios", "Schemes"]
        st.dataframe(cat_df, use_container_width=True, hide_index=True)

        # AUM pie chart
        st.subheader("AUM Composition")
        chart_df = cat_df.set_index("Category")[["AUM (Cr)"]]
        st.bar_chart(chart_df, use_container_width=True, horizontal=True)


elif page == "QAAUM Rankings":
    st.title("QAAUM — Fund House Rankings")

    qdf = load_qaaum_data()
    latest_period = qdf["period_start"].max()
    st.caption(f"Latest period: {latest_period.strftime('%B %Y')}")

    # Top N selector
    top_n = st.slider("Show top N fund houses", 5, 30, 15)

    latest_qaaum = (
        qdf[qdf["period_start"] == latest_period]
        .sort_values("aaum_total_cr", ascending=False)
        .head(top_n)[["fund_house", "aaum_total_cr"]]
    )
    latest_qaaum.columns = ["Fund House", "AAUM (Cr)"]

    st.bar_chart(latest_qaaum.set_index("Fund House"), use_container_width=True)
    st.dataframe(latest_qaaum, use_container_width=True, hide_index=True)

    # Trend for selected fund house
    st.subheader("Fund House Trend")
    all_houses = sorted(qdf["fund_house"].unique())
    selected_house = st.selectbox("Select Fund House", all_houses, index=all_houses.index("HDFC Mutual Fund") if "HDFC Mutual Fund" in all_houses else 0)

    house_trend = (
        qdf[qdf["fund_house"] == selected_house]
        .sort_values("period_start")[["period_start", "aaum_total_cr"]]
        .set_index("period_start")
    )
    st.line_chart(house_trend, use_container_width=True)


elif page == "Data Explorer":
    st.title("Data Explorer")
    st.caption("Browse raw monthly data with filters")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        months_list = sorted(df["report_month"].unique(), reverse=True)
        selected_month = st.selectbox("Month", months_list, format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"))
    with col2:
        sections = ["All"] + sorted(df["section"].unique().tolist())
        selected_section = st.selectbox("Section", sections)
    with col3:
        groups_list = ["All"] + sorted(df["group"].dropna().unique().tolist())
        selected_group_filter = st.selectbox("Group", groups_list)

    filtered = df[df["report_month"] == selected_month].copy()
    if selected_section != "All":
        filtered = filtered[filtered["section"] == selected_section]
    if selected_group_filter != "All":
        filtered = filtered[filtered["group"] == selected_group_filter]

    display_cols = ["category", "section", "group", "aum_cr", "net_flow_cr", "funds_mobilized_cr", "redemption_cr", "num_folios", "num_schemes"]
    filtered = filtered[display_cols].sort_values("aum_cr", ascending=False)
    filtered.columns = ["Category", "Section", "Group", "AUM (Cr)", "Net Flow (Cr)", "Mobilized (Cr)", "Redemption (Cr)", "Folios", "Schemes"]

    st.dataframe(filtered, use_container_width=True, hide_index=True)

    st.download_button(
        "Download as CSV",
        filtered.to_csv(index=False),
        file_name=f"mf_industry_{pd.Timestamp(selected_month).strftime('%Y_%m')}.csv",
        mime="text/csv",
    )
