import streamlit as st
import pandas as pd
import altair as alt
from dotenv import load_dotenv
from supabase import create_client
import os

load_dotenv()

st.set_page_config(
    page_title="MF Industry",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Supabase ---

@st.cache_resource
def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def fetch_all(table_name, order_col, desc=True):
    """Fetch all rows from a Supabase table, paginating past the 1000-row limit."""
    supabase = get_supabase()
    all_data = []
    page_size = 1000
    offset = 0
    while True:
        q = supabase.table(table_name).select("*").order(order_col, desc=desc)
        q = q.range(offset, offset + page_size - 1)
        result = q.execute()
        all_data.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size
    return all_data


# --- Data loaders ---

@st.cache_data(ttl=3600)
def load_monthly():
    data = fetch_all("amfi_monthly_detailed", "report_month")
    df = pd.DataFrame(data)
    df["report_month"] = pd.to_datetime(df["report_month"])
    for col in ["aum_cr", "net_flow_cr", "funds_mobilized_cr", "redemption_cr", "avg_aum_cr"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["num_folios", "num_schemes"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=3600)
def load_qaaum():
    data = fetch_all("qaaum_fundwise", "period_start")
    df = pd.DataFrame(data)
    df["period_start"] = pd.to_datetime(df["period_start"])
    for col in ["aaum_total_cr", "aaum_excl_cr", "aaum_fof_cr"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=3600)
def load_metrics():
    data = fetch_all("mf_industry_metrics", "period_date")
    df = pd.DataFrame(data)
    df["period_date"] = pd.to_datetime(df["period_date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@st.cache_data(ttl=3600)
def load_state_data():
    supabase = get_supabase()
    result = supabase.table("mf_state_data").select("*").execute()
    df = pd.DataFrame(result.data)
    df["value_pct"] = pd.to_numeric(df["value_pct"], errors="coerce")
    return df


@st.cache_data(ttl=3600)
def load_maaum():
    data = fetch_all("maaum_classified", "report_month")
    mdf = pd.DataFrame(data)
    mdf["report_month"] = pd.to_datetime(mdf["report_month"])
    for col in ["retail_cr", "corporates_cr", "banks_fis_cr", "fiis_fpis_cr", "hni_cr", "total_cr"]:
        mdf[col] = pd.to_numeric(mdf[col], errors="coerce")
    mdf["individual_cr"] = mdf["retail_cr"] + mdf["hni_cr"]
    mdf["institutional_cr"] = mdf["corporates_cr"] + mdf["banks_fis_cr"] + mdf["fiis_fpis_cr"]
    return mdf


# Active/Passive classification
PASSIVE_GROUPS = {"ETF", "Index"}

# Category group → asset class mapping for display
ASSET_CLASS_MAP = {
    "Equity": "Equity", "Liquid": "Liquid", "Debt": "Debt",
    "Hybrid": "Hybrid", "ETF": "ETF", "FOF": "FOF",
    "Index": "Index", "Solution": "Solution", "Other": "Other",
}


# --- Formatting ---

def fmt_cr(val):
    if pd.isna(val):
        return "—"
    if abs(val) >= 100000:
        return f"₹{val / 100000:,.1f}L Cr"
    if abs(val) >= 1000:
        return f"₹{val / 1000:,.1f}K Cr"
    return f"₹{val:,.0f} Cr"


def fmt_cr_short(val):
    if pd.isna(val):
        return "—"
    if abs(val) >= 100000:
        return f"{val / 100000:,.1f}L"
    if abs(val) >= 1000:
        return f"{val / 1000:,.1f}K"
    return f"{val:,.0f}"


def fmt_num(val):
    if pd.isna(val):
        return "—"
    if abs(val) >= 10000000:
        return f"{val / 10000000:,.2f} Cr"
    if abs(val) >= 100000:
        return f"{val / 100000:,.1f}L"
    if abs(val) >= 1000:
        return f"{val / 1000:,.1f}K"
    return f"{val:,.0f}"


def fmt_pct(val):
    if pd.isna(val):
        return "—"
    return f"{val:+.1f}%"


def pct_change(new, old):
    if pd.isna(new) or pd.isna(old) or old == 0:
        return None
    return ((new / old) - 1) * 100


def y_axis_lakhs_cr(title=""):
    return alt.Axis(
        title=title,
        format="~s",
        labelExpr="datum.value >= 100000 ? format(datum.value / 100000, '.0f') + 'L Cr' : datum.value >= 1000 ? format(datum.value / 1000, '.0f') + 'K Cr' : format(datum.value, '.0f') + ' Cr'"
    )


GROUPS = ["Equity", "Debt", "Hybrid", "Solution Oriented", "Other"]
GROUP_COLORS = {
    "Equity": "#4ade80",
    "Debt": "#60a5fa",
    "Hybrid": "#f59e0b",
    "Solution Oriented": "#a78bfa",
    "Other": "#94a3b8",
}


# --- Sidebar ---

st.sidebar.title("MF Industry")
st.sidebar.caption("Indian Mutual Fund Industry")

page = st.sidebar.radio(
    "Navigate",
    ["Industry Pulse", "Flows", "Categories", "Market Share", "MAAUM", "Industry Story", "Geography", "Scheme Portfolios", "Data Explorer"],
    label_visibility="collapsed",
)

# --- Load core data ---

df = load_monthly()
latest_month = df["report_month"].max()
prev_month = latest_month - pd.DateOffset(months=1)
year_ago = latest_month - pd.DateOffset(months=12)


# =====================================================================
# PAGE: INDUSTRY PULSE
# =====================================================================

if page == "Industry Pulse":
    st.title("Industry Pulse")
    st.caption(f"Data as of {latest_month.strftime('%B %Y')}")

    gt = df[(df["report_month"] == latest_month) & (df["category"] == "Grand Total")]
    gt_prev = df[(df["report_month"] == prev_month) & (df["category"] == "Grand Total")]
    gt_yoy = df[(df["report_month"] == year_ago) & (df["category"] == "Grand Total")]

    if not gt.empty:
        r = gt.iloc[0]
        rp = gt_prev.iloc[0] if not gt_prev.empty else None
        ry = gt_yoy.iloc[0] if not gt_yoy.empty else None

        # KPI row
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total AUM", fmt_cr(r["aum_cr"]),
                   delta=f"{pct_change(r['aum_cr'], rp['aum_cr']):.1f}% MoM" if rp is not None else None)
        c2.metric("YoY Growth", f"{pct_change(r['aum_cr'], ry['aum_cr']):.1f}%" if ry is not None else "—")
        c3.metric("Net Flows", fmt_cr(r["net_flow_cr"]),
                   delta=f"{fmt_cr_short(rp['net_flow_cr'])} Cr prev" if rp is not None else None)
        c4.metric("Folios", fmt_num(r["num_folios"]),
                   delta=f"{fmt_num(r['num_folios'] - rp['num_folios'])} new" if rp is not None and not pd.isna(rp['num_folios']) else None)
        c5.metric("Schemes", fmt_num(r["num_schemes"]))

    # AUM trend — Altair with proper axis
    st.subheader("AUM Trend")
    aum_trend = (
        df[df["category"] == "Grand Total"]
        .sort_values("report_month")[["report_month", "aum_cr"]]
        .rename(columns={"report_month": "Month", "aum_cr": "AUM"})
    )
    chart = alt.Chart(aum_trend).mark_area(
        color="#4ade80", opacity=0.6, line={"color": "#4ade80"}
    ).encode(
        x=alt.X("Month:T", title=""),
        y=alt.Y("AUM:Q", axis=y_axis_lakhs_cr()),
        tooltip=[
            alt.Tooltip("Month:T", format="%B %Y"),
            alt.Tooltip("AUM:Q", format=",.0f", title="AUM (Cr)"),
        ],
    ).properties(height=350)
    st.altair_chart(chart, use_container_width=True)

    # Group breakdown with shares — aggregate from sub-categories
    st.subheader("AUM by Group")
    open_ended = df[
        (df["report_month"] == latest_month)
        & (df["section"] == "Open Ended")
        & (df["group"].isin(GROUPS))
        & (~df["category"].isin(["Grand Total"]))
    ]
    group_latest = open_ended.groupby("group").agg(
        aum_cr=("aum_cr", "sum"), net_flow_cr=("net_flow_cr", "sum"), num_folios=("num_folios", "sum"),
    ).reset_index().rename(columns={"group": "category"})
    total_aum = group_latest["aum_cr"].sum()
    group_latest["share"] = (group_latest["aum_cr"] / total_aum * 100).round(1)

    # YoY growth per group
    open_yoy = df[
        (df["report_month"] == year_ago)
        & (df["section"] == "Open Ended")
        & (df["group"].isin(GROUPS))
    ]
    group_yoy = open_yoy.groupby("group")["aum_cr"].sum().reset_index().rename(columns={"group": "category", "aum_cr": "aum_yoy"})
    group_latest = group_latest.merge(group_yoy, on="category", how="left")
    group_latest["yoy_growth"] = ((group_latest["aum_cr"] / group_latest["aum_yoy"] - 1) * 100).round(1)

    display = group_latest.sort_values("aum_cr", ascending=False)[
        ["category", "aum_cr", "share", "net_flow_cr", "yoy_growth", "num_folios"]
    ].copy()
    display.columns = ["Group", "AUM (Cr)", "Share %", "Net Flow (Cr)", "YoY Growth %", "Folios"]
    st.dataframe(
        display.style.format({
            "AUM (Cr)": "{:,.0f}",
            "Share %": "{:.1f}%",
            "Net Flow (Cr)": "{:,.0f}",
            "YoY Growth %": "{:+.1f}%",
            "Folios": "{:,.0f}",
        }),
        use_container_width=True, hide_index=True,
    )

    # Group composition over time
    st.subheader("Group Composition Over Time")
    open_all = df[(df["section"] == "Open Ended") & (df["group"].isin(GROUPS))]
    comp = open_all.groupby(["report_month", "group"])["aum_cr"].sum().reset_index().rename(columns={"group": "category"})
    monthly_totals = comp.groupby("report_month")["aum_cr"].sum().rename("total")
    comp = comp.merge(monthly_totals, on="report_month")
    comp["share"] = (comp["aum_cr"] / comp["total"] * 100).round(1)

    comp_chart = alt.Chart(comp).mark_area().encode(
        x=alt.X("report_month:T", title=""),
        y=alt.Y("share:Q", stack="normalize", title="Share of AUM", axis=alt.Axis(format="%")),
        color=alt.Color("category:N", title="Group",
                        scale=alt.Scale(domain=list(GROUP_COLORS.keys()), range=list(GROUP_COLORS.values()))),
        tooltip=[
            alt.Tooltip("report_month:T", format="%B %Y", title="Month"),
            alt.Tooltip("category:N", title="Group"),
            alt.Tooltip("share:Q", format=".1f", title="Share %"),
        ],
    ).properties(height=300)
    st.altair_chart(comp_chart, use_container_width=True)


# =====================================================================
# PAGE: FLOWS
# =====================================================================

elif page == "Flows":
    st.title("Flow Tracker")
    st.caption(f"Data as of {latest_month.strftime('%B %Y')}")

    n_months = st.slider("Trailing months", 6, 84, 24, key="flow_months")
    cutoff = latest_month - pd.DateOffset(months=n_months)

    # Net flows by group — aggregate from sub-categories
    st.subheader("Net Flows by Group")
    flow_raw = df[
        (df["report_month"] > cutoff) & (df["section"] == "Open Ended") & (df["group"].isin(GROUPS))
    ]
    flow_df = flow_raw.groupby(["report_month", "group"])["net_flow_cr"].sum().reset_index().rename(columns={"group": "category"})

    flow_chart = alt.Chart(flow_df).mark_bar().encode(
        x=alt.X("yearmonth(report_month):T", title=""),
        y=alt.Y("net_flow_cr:Q", axis=y_axis_lakhs_cr("Net Flow")),
        color=alt.Color("category:N", title="Group",
                        scale=alt.Scale(domain=list(GROUP_COLORS.keys()), range=list(GROUP_COLORS.values()))),
        tooltip=[
            alt.Tooltip("report_month:T", format="%B %Y"),
            alt.Tooltip("category:N", title="Group"),
            alt.Tooltip("net_flow_cr:Q", format=",.0f", title="Net Flow (Cr)"),
        ],
    ).properties(height=400)
    st.altair_chart(flow_chart, use_container_width=True)

    # Flow summary — latest month
    st.subheader("Latest Month Summary")
    latest_flow_raw = df[
        (df["report_month"] == latest_month) & (df["section"] == "Open Ended") & (df["group"].isin(GROUPS))
    ]
    latest_flow = latest_flow_raw.groupby("group").agg(
        funds_mobilized_cr=("funds_mobilized_cr", "sum"),
        redemption_cr=("redemption_cr", "sum"),
        net_flow_cr=("net_flow_cr", "sum"),
    ).reset_index().rename(columns={"group": "category"})
    latest_flow["redemption_ratio"] = (latest_flow["redemption_cr"] / latest_flow["funds_mobilized_cr"] * 100).round(1)
    latest_flow = latest_flow.sort_values("net_flow_cr", ascending=False)
    latest_flow.columns = ["Group", "Gross Sales (Cr)", "Redemptions (Cr)", "Net Flow (Cr)", "Redemption Ratio %"]
    st.dataframe(
        latest_flow.style.format({
            "Gross Sales (Cr)": "{:,.0f}",
            "Redemptions (Cr)": "{:,.0f}",
            "Net Flow (Cr)": "{:,.0f}",
            "Redemption Ratio %": "{:.1f}%",
        }),
        use_container_width=True, hide_index=True,
    )

    # Category-level flow momentum — top gainers and losers
    st.subheader("Category Flow Momentum — Top Gainers & Losers")
    cat_flows = df[
        (df["report_month"] == latest_month)
        & (df["section"] == "Open Ended")
        & (~df["category"].isin(GROUPS + ["Grand Total", "Total A-Open ended Schemes"]))
    ][["category", "net_flow_cr", "aum_cr"]].copy()
    cat_flows["flow_to_aum"] = (cat_flows["net_flow_cr"] / cat_flows["aum_cr"] * 100).round(2)
    cat_flows = cat_flows.sort_values("net_flow_cr", ascending=False)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Top 5 Inflows**")
        top5 = cat_flows.head(5)[["category", "net_flow_cr", "flow_to_aum"]].copy()
        top5.columns = ["Category", "Net Flow (Cr)", "Flow/AUM %"]
        st.dataframe(top5.style.format({"Net Flow (Cr)": "{:,.0f}", "Flow/AUM %": "{:.2f}%"}),
                     use_container_width=True, hide_index=True)
    with col2:
        st.markdown("**Top 5 Outflows**")
        bot5 = cat_flows.tail(5).sort_values("net_flow_cr")[["category", "net_flow_cr", "flow_to_aum"]].copy()
        bot5.columns = ["Category", "Net Flow (Cr)", "Flow/AUM %"]
        st.dataframe(bot5.style.format({"Net Flow (Cr)": "{:,.0f}", "Flow/AUM %": "{:.2f}%"}),
                     use_container_width=True, hide_index=True)


# =====================================================================
# PAGE: CATEGORIES
# =====================================================================

elif page == "Categories":
    st.title("Category Deep Dive")
    st.caption(f"Data as of {latest_month.strftime('%B %Y')}")

    selected_group = st.selectbox("Select Group", GROUPS)

    # Sub-categories in this group
    cat_df = df[
        (df["report_month"] == latest_month)
        & (df["group"] == selected_group)
        & (~df["category"].isin(GROUPS + ["Grand Total", "Total A-Open ended Schemes", "Close Ended Schemes Total", "Interval Schemes Total"]))
        & (df["section"] == "Open Ended")
    ][["category", "aum_cr", "net_flow_cr", "num_folios", "num_schemes"]].copy()

    if cat_df.empty:
        st.info("No sub-category data for this group.")
    else:
        # Compute share within group
        group_aum = cat_df["aum_cr"].sum()
        cat_df["share"] = (cat_df["aum_cr"] / group_aum * 100).round(1)

        # YoY
        cat_yoy = df[
            (df["report_month"] == year_ago)
            & (df["group"] == selected_group)
            & (df["section"] == "Open Ended")
        ][["category", "aum_cr"]].rename(columns={"aum_cr": "aum_yoy"})
        cat_df = cat_df.merge(cat_yoy, on="category", how="left")
        cat_df["yoy"] = ((cat_df["aum_cr"] / cat_df["aum_yoy"] - 1) * 100).round(1)
        cat_df = cat_df.sort_values("aum_cr", ascending=False)

        display = cat_df[["category", "aum_cr", "share", "net_flow_cr", "yoy", "num_folios", "num_schemes"]].copy()
        display.columns = ["Category", "AUM (Cr)", "Share %", "Net Flow (Cr)", "YoY %", "Folios", "Schemes"]
        st.dataframe(
            display.style.format({
                "AUM (Cr)": "{:,.0f}", "Share %": "{:.1f}%", "Net Flow (Cr)": "{:,.0f}",
                "YoY %": "{:+.1f}%", "Folios": "{:,.0f}", "Schemes": "{:,.0f}",
            }),
            use_container_width=True, hide_index=True,
        )

        # Category trend
        st.subheader("Category AUM Trend")
        selected_cat = st.selectbox("Select Category", cat_df["category"].tolist())
        cat_trend = (
            df[(df["category"] == selected_cat) & (df["section"] == "Open Ended")]
            .sort_values("report_month")[["report_month", "aum_cr", "net_flow_cr"]]
        )

        col1, col2 = st.columns(2)
        with col1:
            aum_chart = alt.Chart(cat_trend).mark_area(color="#4ade80", opacity=0.5, line={"color": "#4ade80"}).encode(
                x=alt.X("report_month:T", title=""),
                y=alt.Y("aum_cr:Q", axis=y_axis_lakhs_cr("AUM")),
                tooltip=[alt.Tooltip("report_month:T", format="%B %Y"), alt.Tooltip("aum_cr:Q", format=",.0f", title="AUM (Cr)")],
            ).properties(height=250, title="AUM")
            st.altair_chart(aum_chart, use_container_width=True)
        with col2:
            flow_chart = alt.Chart(cat_trend).mark_bar(color="#60a5fa").encode(
                x=alt.X("report_month:T", title=""),
                y=alt.Y("net_flow_cr:Q", axis=y_axis_lakhs_cr("Net Flow")),
                tooltip=[alt.Tooltip("report_month:T", format="%B %Y"), alt.Tooltip("net_flow_cr:Q", format=",.0f", title="Net Flow (Cr)")],
            ).properties(height=250, title="Net Flows")
            st.altair_chart(flow_chart, use_container_width=True)

        # Share of total industry AUM over time
        st.subheader(f"{selected_cat} — Share of Industry AUM")
        cat_share = df[
            (df["category"] == selected_cat) & (df["section"] == "Open Ended")
        ][["report_month", "aum_cr"]].copy()
        gt_aum = df[df["category"] == "Grand Total"][["report_month", "aum_cr"]].rename(columns={"aum_cr": "total_aum"})
        cat_share = cat_share.merge(gt_aum, on="report_month")
        cat_share["share"] = (cat_share["aum_cr"] / cat_share["total_aum"] * 100).round(2)
        share_chart = alt.Chart(cat_share).mark_line(color="#f59e0b", strokeWidth=2).encode(
            x=alt.X("report_month:T", title=""),
            y=alt.Y("share:Q", title="Share of Industry %", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("report_month:T", format="%B %Y"), alt.Tooltip("share:Q", format=".2f", title="Share %")],
        ).properties(height=200)
        st.altair_chart(share_chart, use_container_width=True)


# =====================================================================
# PAGE: MARKET SHARE
# =====================================================================

elif page == "Market Share":
    st.title("Market Share — Fund Houses")

    qdf = load_qaaum()
    latest_period = qdf["period_start"].max()
    st.caption(f"QAAUM data as of {latest_period.strftime('%B %Y')}")

    # Top N rankings
    top_n = st.slider("Top fund houses", 5, 30, 15)
    latest_q = qdf[qdf["period_start"] == latest_period].sort_values("aaum_total_cr", ascending=False)
    industry_total = latest_q["aaum_total_cr"].sum()

    top = latest_q.head(top_n).copy()
    top["share"] = (top["aaum_total_cr"] / industry_total * 100).round(2)

    # Previous period for share change
    periods_sorted = sorted(qdf["period_start"].unique())
    if len(periods_sorted) >= 2:
        prev_period = periods_sorted[-2]
        prev_q = qdf[qdf["period_start"] == prev_period].set_index("fund_house")["aaum_total_cr"]
        prev_total = prev_q.sum()
        top["prev_share"] = top["fund_house"].map(lambda x: (prev_q.get(x, 0) / prev_total * 100) if prev_total > 0 else 0).round(2)
        top["share_change"] = (top["share"] - top["prev_share"]).round(2)
    else:
        top["share_change"] = 0

    # Bar chart
    bar = alt.Chart(top).mark_bar(color="#4ade80").encode(
        x=alt.X("aaum_total_cr:Q", axis=y_axis_lakhs_cr("AAUM"), title="AAUM"),
        y=alt.Y("fund_house:N", sort="-x", title=""),
        tooltip=[
            alt.Tooltip("fund_house:N", title="Fund House"),
            alt.Tooltip("aaum_total_cr:Q", format=",.0f", title="AAUM (Cr)"),
            alt.Tooltip("share:Q", format=".2f", title="Market Share %"),
        ],
    ).properties(height=top_n * 28 + 50)
    st.altair_chart(bar, use_container_width=True)

    # Table
    display_q = top[["fund_house", "aaum_total_cr", "share", "share_change"]].copy()
    display_q.columns = ["Fund House", "AAUM (Cr)", "Share %", "Change (bps)"]
    display_q["Change (bps)"] = (display_q["Change (bps)"] * 100).round(0)
    st.dataframe(
        display_q.style.format({
            "AAUM (Cr)": "{:,.0f}", "Share %": "{:.2f}%", "Change (bps)": "{:+.0f}",
        }),
        use_container_width=True, hide_index=True,
    )

    # Concentration — top 5 and top 10 over time
    st.subheader("Industry Concentration")
    concentration = []
    for period in sorted(qdf["period_start"].unique()):
        period_data = qdf[qdf["period_start"] == period].sort_values("aaum_total_cr", ascending=False)
        total = period_data["aaum_total_cr"].sum()
        if total > 0:
            top5 = period_data.head(5)["aaum_total_cr"].sum() / total * 100
            top10 = period_data.head(10)["aaum_total_cr"].sum() / total * 100
            concentration.append({"period": period, "Top 5": top5, "Top 10": top10})
    conc_df = pd.DataFrame(concentration)
    conc_melt = conc_df.melt(id_vars="period", var_name="Metric", value_name="Share %")

    conc_chart = alt.Chart(conc_melt).mark_line(strokeWidth=2).encode(
        x=alt.X("period:T", title=""),
        y=alt.Y("Share %:Q", title="Share of Industry AUM %", scale=alt.Scale(zero=False)),
        color=alt.Color("Metric:N", scale=alt.Scale(domain=["Top 5", "Top 10"], range=["#4ade80", "#60a5fa"])),
        tooltip=[
            alt.Tooltip("period:T", format="%B %Y"),
            alt.Tooltip("Metric:N"),
            alt.Tooltip("Share %:Q", format=".1f"),
        ],
    ).properties(height=300)
    st.altair_chart(conc_chart, use_container_width=True)

    # Fund house trend comparison
    st.subheader("Compare Fund Houses")
    all_houses = sorted(qdf["fund_house"].unique())
    defaults = ["HDFC Mutual Fund", "SBI Mutual Fund", "ICICI Prudential Mutual Fund"]
    defaults = [h for h in defaults if h in all_houses]
    selected_houses = st.multiselect("Select fund houses", all_houses, default=defaults)

    if selected_houses:
        compare = qdf[qdf["fund_house"].isin(selected_houses)].sort_values("period_start")
        compare_chart = alt.Chart(compare).mark_line(strokeWidth=2).encode(
            x=alt.X("period_start:T", title=""),
            y=alt.Y("aaum_total_cr:Q", axis=y_axis_lakhs_cr("AAUM")),
            color=alt.Color("fund_house:N", title="Fund House"),
            tooltip=[
                alt.Tooltip("period_start:T", format="%B %Y"),
                alt.Tooltip("fund_house:N"),
                alt.Tooltip("aaum_total_cr:Q", format=",.0f", title="AAUM (Cr)"),
            ],
        ).properties(height=350)
        st.altair_chart(compare_chart, use_container_width=True)


# =====================================================================
# PAGE: MAAUM
# =====================================================================

elif page == "MAAUM":
    st.title("MAAUM — Classified Average AUM")

    maaum = load_maaum()
    maaum_months = sorted(maaum["report_month"].unique())
    maaum_latest = maaum_months[-1]
    st.caption(f"Data as of {pd.Timestamp(maaum_latest).strftime('%B %Y')} · Source: AMFI")

    # AMC list (excluding industry total mf_id=0)
    amc_list = (
        maaum[(maaum["report_month"] == maaum_latest) & (maaum["mf_id"] != 0)]
        .groupby(["mf_id", "mf_name"])["total_cr"].sum()
        .reset_index()
        .sort_values("total_cr", ascending=False)
    )
    amc_names = amc_list["mf_name"].tolist()

    tab_names = ["Composition", "AMC Ranking", "Asset", "Scheme Category", "Investor Type", "Distribution", "Composition Trend"]
    tabs = st.tabs(tab_names)

    # Helper: aggregate by dimension for a given month
    def amc_aum(data, month):
        return data[(data["report_month"] == month) & (data["mf_id"] != 0)].groupby("mf_name")["total_cr"].sum()

    # Helper: get industry total for a month
    def industry_total(data, month):
        return data[(data["report_month"] == month) & (data["mf_id"] == 0)]["total_cr"].sum()

    # ---- Tab 1: Composition ----
    with tabs[0]:
        sel_month_comp = st.selectbox(
            "Month", maaum_months[::-1],
            format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
            key="comp_month"
        )
        md = maaum[maaum["report_month"] == sel_month_comp]
        amcs = md[md["mf_id"] != 0]

        # Build composition table
        comp_rows = []
        for mf_name in amc_names[:16]:
            a = amcs[amcs["mf_name"] == mf_name]
            total = a["total_cr"].sum()
            if total == 0:
                continue

            # Active vs Passive
            passive = a[a["category_group"].isin(PASSIVE_GROUPS)]["total_cr"].sum()
            active_pct = (total - passive) / total * 100 if total else 0

            # Asset class shares
            equity = a[a["category_group"] == "Equity"]["total_cr"].sum() / total * 100
            debt_liq = a[a["category_group"].isin(["Debt", "Liquid"])]["total_cr"].sum() / total * 100
            etf = a[a["category_group"] == "ETF"]["total_cr"].sum() / total * 100

            # Individual vs Institutional
            indiv = a["individual_cr"].sum() / total * 100

            # B30
            b30 = a[a["geography"] == "B15"]["total_cr"].sum() / total * 100

            # Distribution channels
            direct = a[a["dist_channel"] == "TDP"]["total_cr"].sum() / total * 100
            assoc = a[a["dist_channel"] == "TAD"]["total_cr"].sum() / total * 100
            non_assoc = a[a["dist_channel"] == "TNAD"]["total_cr"].sum() / total * 100

            comp_rows.append({
                "AMC": mf_name.replace(" Mutual Fund", " MF"),
                "AUM (Cr)": total,
                "Active%": active_pct,
                "Equity%": equity,
                "Debt%": debt_liq,
                "ETF%": etf,
                "Individual%": indiv,
                "B30%": b30,
                "Direct%": direct,
                "Assoc Dist%": assoc,
                "Non-Assoc%": non_assoc,
            })

        # Add Total row
        ind_total = md[md["mf_id"] == 0]
        if not ind_total.empty:
            t = ind_total["total_cr"].sum()
            comp_rows.append({
                "AMC": "TOTAL (Industry)",
                "AUM (Cr)": t,
                "Active%": (t - ind_total[ind_total["category_group"].isin(PASSIVE_GROUPS)]["total_cr"].sum()) / t * 100 if t else 0,
                "Equity%": ind_total[ind_total["category_group"] == "Equity"]["total_cr"].sum() / t * 100,
                "Debt%": ind_total[ind_total["category_group"].isin(["Debt", "Liquid"])]["total_cr"].sum() / t * 100,
                "ETF%": ind_total[ind_total["category_group"] == "ETF"]["total_cr"].sum() / t * 100,
                "Individual%": ind_total["individual_cr"].sum() / t * 100,
                "B30%": ind_total[ind_total["geography"] == "B15"]["total_cr"].sum() / t * 100,
                "Direct%": ind_total[ind_total["dist_channel"] == "TDP"]["total_cr"].sum() / t * 100,
                "Assoc Dist%": ind_total[ind_total["dist_channel"] == "TAD"]["total_cr"].sum() / t * 100,
                "Non-Assoc%": ind_total[ind_total["dist_channel"] == "TNAD"]["total_cr"].sum() / t * 100,
            })

        comp_df = pd.DataFrame(comp_rows)
        st.dataframe(
            comp_df.style.format({
                "AUM (Cr)": "{:,.0f}",
                "Active%": "{:.1f}%", "Equity%": "{:.1f}%", "Debt%": "{:.1f}%",
                "ETF%": "{:.1f}%", "Individual%": "{:.1f}%", "B30%": "{:.1f}%",
                "Direct%": "{:.1f}%", "Assoc Dist%": "{:.1f}%", "Non-Assoc%": "{:.1f}%",
            }),
            use_container_width=True, hide_index=True,
        )

    # ---- Tab 2: AMC Ranking ----
    with tabs[1]:
        st.subheader("AMC Ranking by AUM")
        col1, col2 = st.columns(2)
        with col1:
            rank_start = st.selectbox(
                "Growth from", maaum_months,
                index=max(0, len(maaum_months) - 12),
                format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
                key="rank_start"
            )
        with col2:
            rank_end = st.selectbox(
                "Growth to", maaum_months[::-1],
                format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
                key="rank_end"
            )

        end_data = maaum[(maaum["report_month"] == rank_end) & (maaum["mf_id"] != 0)]
        start_data = maaum[(maaum["report_month"] == rank_start) & (maaum["mf_id"] != 0)]

        end_aum = end_data.groupby("mf_name")["total_cr"].sum().reset_index().rename(columns={"total_cr": "aum"})
        start_aum = start_data.groupby("mf_name")["total_cr"].sum().reset_index().rename(columns={"total_cr": "aum_start"})

        rank_df = end_aum.merge(start_aum, on="mf_name", how="left")
        ind_end = industry_total(maaum, rank_end)
        ind_start = industry_total(maaum, rank_start)
        ind_growth = ind_end - ind_start

        rank_df["share"] = (rank_df["aum"] / ind_end * 100).round(2)
        rank_df["growth"] = rank_df["aum"] - rank_df["aum_start"].fillna(0)
        rank_df["growth_share"] = (rank_df["growth"] / ind_growth * 100).round(2) if ind_growth > 0 else 0
        rank_df = rank_df.sort_values("aum", ascending=False).reset_index(drop=True)
        rank_df["aum_rank"] = range(1, len(rank_df) + 1)
        rank_df["growth_rank"] = rank_df["growth"].rank(ascending=False, method="min").astype(int)

        display_rank = rank_df[["mf_name", "aum", "share", "growth", "growth_share", "aum_rank", "growth_rank"]].copy()
        display_rank["mf_name"] = display_rank["mf_name"].str.replace(" Mutual Fund", " MF")
        display_rank.columns = ["AMC", "AUM (Cr)", "Market Share%", "AUM Growth (Cr)", "Growth Share%", "AUM Rank", "Growth Rank"]

        st.dataframe(
            display_rank.style.format({
                "AUM (Cr)": "{:,.0f}", "Market Share%": "{:.2f}%",
                "AUM Growth (Cr)": "{:,.0f}", "Growth Share%": "{:.2f}%",
            }),
            use_container_width=True, hide_index=True,
        )

        # Horizontal bar chart — top 15
        bar_data = rank_df.head(15).copy()
        bar_data["mf_name"] = bar_data["mf_name"].str.replace(" Mutual Fund", " MF")
        bar = alt.Chart(bar_data).mark_bar(color="#4ade80").encode(
            x=alt.X("aum:Q", axis=y_axis_lakhs_cr("AUM"), title="AUM (Cr)"),
            y=alt.Y("mf_name:N", sort="-x", title=""),
            tooltip=[
                alt.Tooltip("mf_name:N", title="AMC"),
                alt.Tooltip("aum:Q", format=",.0f", title="AUM (Cr)"),
                alt.Tooltip("share:Q", format=".2f", title="Share %"),
            ],
        ).properties(height=15 * 28 + 50)
        st.altair_chart(bar, use_container_width=True)

    # ---- Tab 3: Asset ----
    with tabs[2]:
        sel_amc_asset = st.selectbox("Select AMC", amc_names, key="asset_amc",
                                     format_func=lambda x: x.replace(" Mutual Fund", " MF"))
        sel_mf_id = amc_list[amc_list["mf_name"] == sel_amc_asset]["mf_id"].values[0]

        col1, col2 = st.columns(2)
        with col1:
            asset_start = st.selectbox("From", maaum_months,
                                       index=max(0, len(maaum_months) - 12),
                                       format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
                                       key="asset_start")
        with col2:
            asset_end = st.selectbox("To", maaum_months[::-1],
                                     format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
                                     key="asset_end")

        def build_asset_table(dimension_col, dimension_map, mf_id, start, end):
            """Build a table with AMC AUM, Industry AUM, Market Share, Growth, Growth Share."""
            rows = []
            for dim_name, filter_fn in dimension_map.items():
                # End period
                amc_end = maaum[(maaum["report_month"] == end) & (maaum["mf_id"] == mf_id)]
                amc_val = filter_fn(amc_end)["total_cr"].sum()
                ind_end_d = maaum[(maaum["report_month"] == end) & (maaum["mf_id"] == 0)]
                ind_val = filter_fn(ind_end_d)["total_cr"].sum()
                mkt_share = (amc_val / ind_val * 100) if ind_val > 0 else 0

                # Start period
                amc_st = maaum[(maaum["report_month"] == start) & (maaum["mf_id"] == mf_id)]
                amc_val_s = filter_fn(amc_st)["total_cr"].sum()
                ind_st_d = maaum[(maaum["report_month"] == start) & (maaum["mf_id"] == 0)]
                ind_val_s = filter_fn(ind_st_d)["total_cr"].sum()

                amc_growth = amc_val - amc_val_s
                ind_growth = ind_val - ind_val_s
                growth_share = (amc_growth / ind_growth * 100) if ind_growth > 0 else 0

                rows.append({
                    dimension_col: dim_name,
                    "AMC AUM (Cr)": amc_val,
                    "Industry AUM (Cr)": ind_val,
                    "Market Share%": mkt_share,
                    "AMC Growth (Cr)": amc_growth,
                    "Industry Growth (Cr)": ind_growth,
                    "Growth Share%": growth_share,
                })
            return pd.DataFrame(rows)

        # Active / Passive
        st.markdown("**Active vs Passive**")
        ap_map = {
            "Active": lambda d: d[~d["category_group"].isin(PASSIVE_GROUPS)],
            "Passive": lambda d: d[d["category_group"].isin(PASSIVE_GROUPS)],
        }
        ap_df = build_asset_table("Type", ap_map, sel_mf_id, asset_start, asset_end)
        st.dataframe(ap_df.style.format({
            "AMC AUM (Cr)": "{:,.0f}", "Industry AUM (Cr)": "{:,.0f}",
            "Market Share%": "{:.2f}%", "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": "{:.2f}%",
        }), use_container_width=True, hide_index=True)

        # Asset Class
        st.markdown("**Asset Class Breakdown**")
        asset_groups = ["Equity", "Debt", "Liquid", "Hybrid", "ETF", "FOF"]
        ac_map = {g: (lambda d, g=g: d[d["category_group"] == g]) for g in asset_groups}
        ac_df = build_asset_table("Asset Class", ac_map, sel_mf_id, asset_start, asset_end)
        ac_df = ac_df[ac_df["AMC AUM (Cr)"] > 0]
        st.dataframe(ac_df.style.format({
            "AMC AUM (Cr)": "{:,.0f}", "Industry AUM (Cr)": "{:,.0f}",
            "Market Share%": "{:.2f}%", "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": "{:.2f}%",
        }), use_container_width=True, hide_index=True)

    # ---- Tab 4: Scheme Category ----
    with tabs[3]:
        sel_amc_cat = st.selectbox("Select AMC", amc_names, key="cat_amc",
                                   format_func=lambda x: x.replace(" Mutual Fund", " MF"))
        sel_mf_id_cat = amc_list[amc_list["mf_name"] == sel_amc_cat]["mf_id"].values[0]

        col1, col2 = st.columns(2)
        with col1:
            cat_start = st.selectbox("From", maaum_months,
                                     index=max(0, len(maaum_months) - 12),
                                     format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
                                     key="cat_start")
        with col2:
            cat_end = st.selectbox("To", maaum_months[::-1],
                                   format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
                                   key="cat_end")

        # Get all categories for this AMC
        cats_end = maaum[(maaum["report_month"] == cat_end) & (maaum["mf_id"] == sel_mf_id_cat)]
        cats_start = maaum[(maaum["report_month"] == cat_start) & (maaum["mf_id"] == sel_mf_id_cat)]
        ind_cats_end = maaum[(maaum["report_month"] == cat_end) & (maaum["mf_id"] == 0)]
        ind_cats_start = maaum[(maaum["report_month"] == cat_start) & (maaum["mf_id"] == 0)]

        cat_rows = []
        for cat in cats_end["category"].unique():
            amc_val = cats_end[cats_end["category"] == cat]["total_cr"].sum()
            if amc_val == 0:
                continue
            ind_val = ind_cats_end[ind_cats_end["category"] == cat]["total_cr"].sum()
            mkt_share = (amc_val / ind_val * 100) if ind_val > 0 else 0

            amc_val_s = cats_start[cats_start["category"] == cat]["total_cr"].sum()
            ind_val_s = ind_cats_start[ind_cats_start["category"] == cat]["total_cr"].sum()
            amc_growth = amc_val - amc_val_s
            ind_growth = ind_val - ind_val_s
            growth_share = (amc_growth / ind_growth * 100) if ind_growth != 0 else 0

            cat_rows.append({
                "Category": cat,
                "AMC AUM (Cr)": amc_val,
                "Industry AUM (Cr)": ind_val,
                "Market Share%": mkt_share,
                "AMC Growth (Cr)": amc_growth,
                "Industry Growth (Cr)": ind_growth,
                "Growth Share%": growth_share,
            })

        cat_df = pd.DataFrame(cat_rows).sort_values("AMC AUM (Cr)", ascending=False)
        st.dataframe(cat_df.style.format({
            "AMC AUM (Cr)": "{:,.0f}", "Industry AUM (Cr)": "{:,.0f}",
            "Market Share%": "{:.2f}%", "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": "{:.2f}%",
        }), use_container_width=True, hide_index=True)

    # ---- Tab 5: Investor Type ----
    with tabs[4]:
        sel_amc_inv = st.selectbox("Select AMC", amc_names, key="inv_amc",
                                   format_func=lambda x: x.replace(" Mutual Fund", " MF"))
        sel_mf_id_inv = amc_list[amc_list["mf_name"] == sel_amc_inv]["mf_id"].values[0]

        col1, col2 = st.columns(2)
        with col1:
            inv_start = st.selectbox("From", maaum_months,
                                     index=max(0, len(maaum_months) - 12),
                                     format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
                                     key="inv_start")
        with col2:
            inv_end = st.selectbox("To", maaum_months[::-1],
                                   format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
                                   key="inv_end")

        # Individual / Institutional
        st.markdown("**Individual vs Institutional**")
        ii_map = {
            "Individual": lambda d: pd.DataFrame({"total_cr": [d["individual_cr"].sum()]}),
            "Institutional": lambda d: pd.DataFrame({"total_cr": [d["institutional_cr"].sum()]}),
        }
        ii_rows = []
        for dim_name, agg_fn in ii_map.items():
            amc_e = maaum[(maaum["report_month"] == inv_end) & (maaum["mf_id"] == sel_mf_id_inv)]
            amc_val = agg_fn(amc_e)["total_cr"].sum()
            ind_e = maaum[(maaum["report_month"] == inv_end) & (maaum["mf_id"] == 0)]
            ind_val = agg_fn(ind_e)["total_cr"].sum()
            mkt_share = (amc_val / ind_val * 100) if ind_val > 0 else 0

            amc_s = maaum[(maaum["report_month"] == inv_start) & (maaum["mf_id"] == sel_mf_id_inv)]
            amc_val_s = agg_fn(amc_s)["total_cr"].sum()
            ind_s = maaum[(maaum["report_month"] == inv_start) & (maaum["mf_id"] == 0)]
            ind_val_s = agg_fn(ind_s)["total_cr"].sum()

            ii_rows.append({
                "Type": dim_name,
                "AMC AUM (Cr)": amc_val, "Industry AUM (Cr)": ind_val,
                "Market Share%": mkt_share,
                "AMC Growth (Cr)": amc_val - amc_val_s,
                "Industry Growth (Cr)": ind_val - ind_val_s,
                "Growth Share%": ((amc_val - amc_val_s) / (ind_val - ind_val_s) * 100) if (ind_val - ind_val_s) != 0 else 0,
            })
        ii_df = pd.DataFrame(ii_rows)
        st.dataframe(ii_df.style.format({
            "AMC AUM (Cr)": "{:,.0f}", "Industry AUM (Cr)": "{:,.0f}",
            "Market Share%": "{:.2f}%", "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": "{:.2f}%",
        }), use_container_width=True, hide_index=True)

        # 5 investor types
        st.markdown("**By Investor Type**")
        inv_cols = [
            ("HNI", "hni_cr"), ("Corporates", "corporates_cr"), ("Retail", "retail_cr"),
            ("Banks/FIs", "banks_fis_cr"), ("FIIs/FPIs", "fiis_fpis_cr"),
        ]
        inv_rows = []
        for inv_name, inv_col in inv_cols:
            amc_e = maaum[(maaum["report_month"] == inv_end) & (maaum["mf_id"] == sel_mf_id_inv)]
            amc_val = amc_e[inv_col].sum()
            ind_e = maaum[(maaum["report_month"] == inv_end) & (maaum["mf_id"] == 0)]
            ind_val = ind_e[inv_col].sum()
            mkt_share = (amc_val / ind_val * 100) if ind_val > 0 else 0

            amc_s = maaum[(maaum["report_month"] == inv_start) & (maaum["mf_id"] == sel_mf_id_inv)]
            amc_val_s = amc_s[inv_col].sum()
            ind_s = maaum[(maaum["report_month"] == inv_start) & (maaum["mf_id"] == 0)]
            ind_val_s = ind_s[inv_col].sum()

            inv_rows.append({
                "Investor Type": inv_name,
                "AMC AUM (Cr)": amc_val, "Industry AUM (Cr)": ind_val,
                "Market Share%": mkt_share,
                "AMC Growth (Cr)": amc_val - amc_val_s,
                "Industry Growth (Cr)": ind_val - ind_val_s,
                "Growth Share%": ((amc_val - amc_val_s) / (ind_val - ind_val_s) * 100) if (ind_val - ind_val_s) != 0 else 0,
            })
        inv_df = pd.DataFrame(inv_rows).sort_values("AMC AUM (Cr)", ascending=False)
        st.dataframe(inv_df.style.format({
            "AMC AUM (Cr)": "{:,.0f}", "Industry AUM (Cr)": "{:,.0f}",
            "Market Share%": "{:.2f}%", "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": "{:.2f}%",
        }), use_container_width=True, hide_index=True)

        # Donut chart for investor composition
        amc_e = maaum[(maaum["report_month"] == inv_end) & (maaum["mf_id"] == sel_mf_id_inv)]
        donut_data = pd.DataFrame([
            {"Type": n, "AUM": amc_e[c].sum()} for n, c in inv_cols
        ])
        donut_data = donut_data[donut_data["AUM"] > 0]
        donut = alt.Chart(donut_data).mark_arc(innerRadius=50).encode(
            theta=alt.Theta("AUM:Q"),
            color=alt.Color("Type:N", scale=alt.Scale(
                domain=["HNI", "Corporates", "Retail", "Banks/FIs", "FIIs/FPIs"],
                range=["#4ade80", "#60a5fa", "#f59e0b", "#a78bfa", "#f472b6"]
            )),
            tooltip=[alt.Tooltip("Type:N"), alt.Tooltip("AUM:Q", format=",.0f", title="AUM (Cr)")],
        ).properties(height=300, title="Investor Composition")
        st.altair_chart(donut, use_container_width=True)

    # ---- Tab 6: Distribution ----
    with tabs[5]:
        sel_amc_dist = st.selectbox("Select AMC", amc_names, key="dist_amc",
                                    format_func=lambda x: x.replace(" Mutual Fund", " MF"))
        sel_mf_id_dist = amc_list[amc_list["mf_name"] == sel_amc_dist]["mf_id"].values[0]

        col1, col2 = st.columns(2)
        with col1:
            dist_start = st.selectbox("From", maaum_months,
                                      index=max(0, len(maaum_months) - 12),
                                      format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
                                      key="dist_start")
        with col2:
            dist_end = st.selectbox("To", maaum_months[::-1],
                                    format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
                                    key="dist_end")

        # Direct / Regular
        st.markdown("**Direct vs Regular**")
        dr_map = {
            "Direct": lambda d: d[d["dist_channel"] == "TDP"],
            "Regular": lambda d: d[d["dist_channel"].isin(["TAD", "TNAD"])],
        }
        dr_df = build_asset_table("Channel", dr_map, sel_mf_id_dist, dist_start, dist_end)
        st.dataframe(dr_df.style.format({
            "AMC AUM (Cr)": "{:,.0f}", "Industry AUM (Cr)": "{:,.0f}",
            "Market Share%": "{:.2f}%", "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": "{:.2f}%",
        }), use_container_width=True, hide_index=True)

        # 3 channels
        st.markdown("**By Distribution Channel**")
        ch_labels = {"TDP": "Direct", "TAD": "Assoc Dist", "TNAD": "Non-Assoc Dist"}
        ch_map = {v: (lambda d, ch=k: d[d["dist_channel"] == ch]) for k, v in ch_labels.items()}
        ch_df = build_asset_table("Channel", ch_map, sel_mf_id_dist, dist_start, dist_end)
        st.dataframe(ch_df.style.format({
            "AMC AUM (Cr)": "{:,.0f}", "Industry AUM (Cr)": "{:,.0f}",
            "Market Share%": "{:.2f}%", "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": "{:.2f}%",
        }), use_container_width=True, hide_index=True)

        # T30 / B30
        st.markdown("**T30 vs B30**")
        geo_map = {
            "T30": lambda d: d[d["geography"] == "T15"],
            "B30": lambda d: d[d["geography"] == "B15"],
        }
        geo_df = build_asset_table("Geography", geo_map, sel_mf_id_dist, dist_start, dist_end)
        st.dataframe(geo_df.style.format({
            "AMC AUM (Cr)": "{:,.0f}", "Industry AUM (Cr)": "{:,.0f}",
            "Market Share%": "{:.2f}%", "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": "{:.2f}%",
        }), use_container_width=True, hide_index=True)

    # ---- Tab 7: Composition Trend ----
    with tabs[6]:
        dim_options = {
            "B30%": ("geography", "B15", "total_cr"),
            "Direct%": ("dist_channel", "TDP", "total_cr"),
            "Individual%": ("investor", None, "individual_cr"),
            "Equity%": ("category_group", "Equity", "total_cr"),
            "Debt%": ("category_group", "Debt", "total_cr"),
            "ETF%": ("category_group", "ETF", "total_cr"),
            "Passive%": ("category_group_set", None, "total_cr"),
            "Active%": ("category_group_set_inv", None, "total_cr"),
        }
        sel_dim = st.selectbox("Breakdown Dimension", list(dim_options.keys()), key="trend_dim")

        def compute_dim_pct(data, mf_id, month, dim_key):
            """Compute the % for a given dimension."""
            d = data[(data["report_month"] == month) & (data["mf_id"] == mf_id)]
            total = d["total_cr"].sum()
            if total == 0:
                return 0
            dim_type, dim_val, col = dim_options[dim_key]
            if dim_type == "geography":
                return d[d["geography"] == dim_val][col].sum() / total * 100
            elif dim_type == "dist_channel":
                return d[d["dist_channel"] == dim_val][col].sum() / total * 100
            elif dim_type == "investor":
                return d[col].sum() / total * 100
            elif dim_type == "category_group":
                return d[d["category_group"] == dim_val][col].sum() / total * 100
            elif dim_type == "category_group_set":
                return d[d["category_group"].isin(PASSIVE_GROUPS)][col].sum() / total * 100
            elif dim_type == "category_group_set_inv":
                return (total - d[d["category_group"].isin(PASSIVE_GROUPS)][col].sum()) / total * 100
            return 0

        # Build trend table: rows = AMCs (top 10, next 10, total), columns = months
        trend_rows = []
        # Get AMC ranking by latest AUM
        latest_ranking = (
            maaum[(maaum["report_month"] == maaum_latest) & (maaum["mf_id"] != 0)]
            .groupby(["mf_id", "mf_name"])["total_cr"].sum()
            .reset_index()
            .sort_values("total_cr", ascending=False)
        )
        ranked_amcs = latest_ranking[["mf_id", "mf_name"]].values.tolist()

        top10 = ranked_amcs[:10]
        next10 = ranked_amcs[10:20]

        for label, group in [("Top 10", top10), ("Next 10", next10)]:
            for mf_id, mf_name in group:
                row = {"AMC": mf_name.replace(" Mutual Fund", " MF")}
                for m in maaum_months:
                    col_label = pd.Timestamp(m).strftime("%b-%y")
                    row[col_label] = round(compute_dim_pct(maaum, mf_id, m, sel_dim), 1)
                trend_rows.append(row)
            # Subtotal for the group
            group_ids = [mid for mid, _ in group]
            sub_row = {"AMC": f"— {label} Subtotal —"}
            for m in maaum_months:
                col_label = pd.Timestamp(m).strftime("%b-%y")
                gd = maaum[(maaum["report_month"] == m) & (maaum["mf_id"].isin(group_ids))]
                gtotal = gd["total_cr"].sum()
                if gtotal == 0:
                    sub_row[col_label] = 0
                else:
                    dim_type, dim_val, col = dim_options[sel_dim]
                    if dim_type == "geography":
                        sub_row[col_label] = round(gd[gd["geography"] == dim_val][col].sum() / gtotal * 100, 1)
                    elif dim_type == "dist_channel":
                        sub_row[col_label] = round(gd[gd["dist_channel"] == dim_val][col].sum() / gtotal * 100, 1)
                    elif dim_type == "investor":
                        sub_row[col_label] = round(gd[col].sum() / gtotal * 100, 1)
                    elif dim_type == "category_group":
                        sub_row[col_label] = round(gd[gd["category_group"] == dim_val][col].sum() / gtotal * 100, 1)
                    elif dim_type == "category_group_set":
                        sub_row[col_label] = round(gd[gd["category_group"].isin(PASSIVE_GROUPS)][col].sum() / gtotal * 100, 1)
                    elif dim_type == "category_group_set_inv":
                        sub_row[col_label] = round((gtotal - gd[gd["category_group"].isin(PASSIVE_GROUPS)][col].sum()) / gtotal * 100, 1)
            trend_rows.append(sub_row)

        # Industry total
        total_row = {"AMC": "TOTAL (Industry)"}
        for m in maaum_months:
            col_label = pd.Timestamp(m).strftime("%b-%y")
            total_row[col_label] = round(compute_dim_pct(maaum, 0, m, sel_dim), 1)
        trend_rows.append(total_row)

        trend_df = pd.DataFrame(trend_rows)
        month_cols = [c for c in trend_df.columns if c != "AMC"]
        fmt_dict = {c: "{:.1f}%" for c in month_cols}
        st.dataframe(
            trend_df.style.format(fmt_dict),
            use_container_width=True, hide_index=True,
        )


# =====================================================================
# PAGE: INDUSTRY STORY
# =====================================================================

elif page == "Industry Story":
    st.title("Industry Story")
    st.caption("Structural trends shaping the Indian mutual fund industry")

    metrics = load_metrics()

    tab_names = ["AUM & Macro", "SIP", "Passive Funds", "Digital", "Women in MF", "Investors", "Global"]
    tabs = st.tabs(tab_names)

    # --- AUM & Macro ---
    with tabs[0]:
        st.subheader("AUM vs GDP")
        aum_gdp = metrics[metrics["metric_name"] == "mf_aum_to_gdp_ratio"].sort_values("period_date")
        if not aum_gdp.empty:
            c = alt.Chart(aum_gdp).mark_bar(color="#4ade80").encode(
                x=alt.X("period_date:T", title=""),
                y=alt.Y("value:Q", title="AUM as % of GDP"),
                tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=".1f", title="%")],
            ).properties(height=250)
            st.altair_chart(c, use_container_width=True)

        st.subheader("AMC Concentration")
        col1, col2 = st.columns(2)
        with col1:
            top5_conc = metrics[metrics["metric_name"] == "amc_concentration_top5"].sort_values("period_date")
            if not top5_conc.empty:
                c = alt.Chart(top5_conc).mark_line(color="#4ade80", strokeWidth=2).encode(
                    x=alt.X("period_date:T", title=""), y=alt.Y("value:Q", title="Top 5 Share %", scale=alt.Scale(zero=False)),
                    tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=".1f")],
                ).properties(height=200, title="Top 5 AMCs")
                st.altair_chart(c, use_container_width=True)
        with col2:
            top10_conc = metrics[metrics["metric_name"] == "amc_concentration_top10"].sort_values("period_date")
            if not top10_conc.empty:
                c = alt.Chart(top10_conc).mark_line(color="#60a5fa", strokeWidth=2).encode(
                    x=alt.X("period_date:T", title=""), y=alt.Y("value:Q", title="Top 10 Share %", scale=alt.Scale(zero=False)),
                    tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=".1f")],
                ).properties(height=200, title="Top 10 AMCs")
                st.altair_chart(c, use_container_width=True)

        st.subheader("Macro Context")
        macro_metrics = ["gdp_growth_rate", "gross_domestic_savings_rate", "gdp_per_capita_nominal"]
        for m in macro_metrics:
            mdata = metrics[metrics["metric_name"] == m].sort_values("period_date")
            if not mdata.empty:
                label = m.replace("_", " ").title()
                unit = mdata.iloc[0]["unit"] if "unit" in mdata.columns else ""
                c = alt.Chart(mdata).mark_line(color="#f59e0b", strokeWidth=2).encode(
                    x=alt.X("period_date:T", title=""),
                    y=alt.Y("value:Q", title=f"{label} ({unit})", scale=alt.Scale(zero=False)),
                    tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=".1f")],
                ).properties(height=180, title=label)
                st.altair_chart(c, use_container_width=True)

    # --- SIP ---
    with tabs[1]:
        st.subheader("SIP Growth")
        sip_aum = metrics[metrics["metric_name"] == "sip_aum"].sort_values("period_date")
        if not sip_aum.empty:
            c = alt.Chart(sip_aum).mark_bar(color="#4ade80").encode(
                x=alt.X("period_date:T", title=""),
                y=alt.Y("value:Q", title="SIP AUM (L Cr)"),
                tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=",.0f")],
            ).properties(height=250)
            st.altair_chart(c, use_container_width=True)

        sip_share = metrics[metrics["metric_name"] == "sip_aum_share_of_industry"].sort_values("period_date")
        if not sip_share.empty:
            c = alt.Chart(sip_share).mark_line(color="#f59e0b", strokeWidth=2).encode(
                x=alt.X("period_date:T", title=""),
                y=alt.Y("value:Q", title="SIP AUM as % of Industry"),
                tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=".1f")],
            ).properties(height=200)
            st.altair_chart(c, use_container_width=True)

    # --- Passive Funds ---
    with tabs[2]:
        st.subheader("Passive Funds Rise")
        passive_share = metrics[metrics["metric_name"] == "passive_aum_share"].sort_values("period_date")
        if not passive_share.empty:
            c = alt.Chart(passive_share).mark_area(color="#a78bfa", opacity=0.5, line={"color": "#a78bfa"}).encode(
                x=alt.X("period_date:T", title=""),
                y=alt.Y("value:Q", title="Passive Share of Industry %"),
                tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=".1f")],
            ).properties(height=250)
            st.altair_chart(c, use_container_width=True)

        passive_aum = metrics[metrics["metric_name"] == "passive_aum"].sort_values("period_date")
        if not passive_aum.empty:
            c = alt.Chart(passive_aum).mark_bar(color="#a78bfa").encode(
                x=alt.X("period_date:T", title=""),
                y=alt.Y("value:Q", title="Passive AUM (L Cr)"),
                tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=",.0f")],
            ).properties(height=250)
            st.altair_chart(c, use_container_width=True)

    # --- Digital ---
    with tabs[3]:
        st.subheader("Digital Adoption")
        for m in ["digital_channel_mf_purchase", "digital_channel_sip_purchase"]:
            mdata = metrics[metrics["metric_name"] == m].sort_values("period_date")
            if not mdata.empty:
                label = m.replace("_", " ").title()
                c = alt.Chart(mdata).mark_bar(color="#60a5fa").encode(
                    x=alt.X("period_date:T", title=""),
                    y=alt.Y("value:Q", title="%"),
                    tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=".1f")],
                ).properties(height=200, title=label)
                st.altair_chart(c, use_container_width=True)

    # --- Women in MF ---
    with tabs[4]:
        st.subheader("Women in Mutual Funds")

        women_aum = metrics[metrics["metric_name"] == "women_aum"].sort_values("period_date")
        if not women_aum.empty:
            c = alt.Chart(women_aum).mark_area(color="#f472b6", opacity=0.5, line={"color": "#f472b6"}).encode(
                x=alt.X("period_date:T", title=""),
                y=alt.Y("value:Q", title="Women's AUM (L Cr)"),
                tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=",.0f")],
            ).properties(height=250)
            st.altair_chart(c, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            w_share = metrics[metrics["metric_name"] == "women_share_individual_aum"].sort_values("period_date")
            if not w_share.empty:
                c = alt.Chart(w_share).mark_line(color="#f472b6", strokeWidth=2).encode(
                    x=alt.X("period_date:T", title=""),
                    y=alt.Y("value:Q", title="%", scale=alt.Scale(zero=False)),
                    tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=".1f")],
                ).properties(height=200, title="Women's Share of Individual AUM")
                st.altair_chart(c, use_container_width=True)
        with col2:
            w_inv = metrics[metrics["metric_name"] == "women_share_unique_investors"].sort_values("period_date")
            if not w_inv.empty:
                c = alt.Chart(w_inv).mark_line(color="#a78bfa", strokeWidth=2).encode(
                    x=alt.X("period_date:T", title=""),
                    y=alt.Y("value:Q", title="%", scale=alt.Scale(zero=False)),
                    tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=".1f")],
                ).properties(height=200, title="Women's Share of Unique Investors")
                st.altair_chart(c, use_container_width=True)

        # Women SIP
        w_sip = metrics[metrics["metric_name"] == "women_sip_aum"].sort_values("period_date")
        if not w_sip.empty:
            c = alt.Chart(w_sip).mark_bar(color="#f472b6").encode(
                x=alt.X("period_date:T", title=""),
                y=alt.Y("value:Q", title="Women SIP AUM (L Cr)"),
                tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=",.0f")],
            ).properties(height=200)
            st.altair_chart(c, use_container_width=True)

    # --- Investors ---
    with tabs[5]:
        st.subheader("Investor Base")
        uniq = metrics[metrics["metric_name"] == "unique_investors"].sort_values("period_date")
        if not uniq.empty:
            c = alt.Chart(uniq).mark_bar(color="#4ade80").encode(
                x=alt.X("period_date:T", title=""),
                y=alt.Y("value:Q", title="Unique Investors (Cr)"),
                tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("value:Q", format=".2f")],
            ).properties(height=250)
            st.altair_chart(c, use_container_width=True)

        # B30 vs T30
        geo = metrics[metrics["metric_name"].isin(["b30_t30_aum_share", "city_tier_aum_share"])].sort_values("period_date")
        if not geo.empty:
            c = alt.Chart(geo).mark_bar().encode(
                x=alt.X("period_date:T", title=""),
                y=alt.Y("value:Q", title="%"),
                color=alt.Color("segment:N", title="Segment"),
                tooltip=[alt.Tooltip("period_date:T", format="%b %Y"), alt.Tooltip("segment:N"), alt.Tooltip("value:Q", format=".1f")],
            ).properties(height=250, title="B30 vs T30 / Geographic Split")
            st.altair_chart(c, use_container_width=True)

    # --- Global ---
    with tabs[6]:
        st.subheader("Global Comparison")
        global_data = metrics[metrics["metric_name"] == "mf_aum_to_gdp_global"].sort_values("value", ascending=False)
        if not global_data.empty:
            c = alt.Chart(global_data).mark_bar(color="#60a5fa").encode(
                x=alt.X("value:Q", title="AUM as % of GDP"),
                y=alt.Y("segment:N", sort="-x", title=""),
                tooltip=[alt.Tooltip("segment:N", title="Country"), alt.Tooltip("value:Q", format=".0f", title="AUM/GDP %")],
            ).properties(height=len(global_data) * 25 + 50)
            st.altair_chart(c, use_container_width=True)

        cagr_data = metrics[metrics["metric_name"] == "regulated_net_assets_5yr_cagr"].sort_values("value", ascending=False)
        if not cagr_data.empty:
            c = alt.Chart(cagr_data).mark_bar(color="#4ade80").encode(
                x=alt.X("value:Q", title="5-Year CAGR %"),
                y=alt.Y("segment:N", sort="-x", title=""),
                tooltip=[alt.Tooltip("segment:N", title="Country"), alt.Tooltip("value:Q", format=".1f", title="CAGR %")],
            ).properties(height=len(cagr_data) * 25 + 50)
            st.altair_chart(c, use_container_width=True)


# =====================================================================
# PAGE: GEOGRAPHY
# =====================================================================

elif page == "Geography":
    st.title("Geography — State-wise Data")

    state_df = load_state_data()
    if state_df.empty:
        st.warning("No state data available.")
    else:
        st.caption("Source: AMFI-CRISIL Factbook 2024 & AMFI Women's Day Report Mar 2025")

        dim = st.selectbox("Select Dimension", ["Women's AUM Share", "Asset Allocation", "Age Groups"])

        if dim == "Women's AUM Share":
            wdata = state_df[state_df["dimension"] == "women_aum_pct"].sort_values("value_pct", ascending=False)
            c = alt.Chart(wdata).mark_bar(color="#f472b6").encode(
                x=alt.X("value_pct:Q", title="Women's Share of Individual AUM %"),
                y=alt.Y("state:N", sort="-x", title=""),
                tooltip=[alt.Tooltip("state:N"), alt.Tooltip("value_pct:Q", format=".1f", title="%")],
            ).properties(height=len(wdata) * 20 + 50)
            st.altair_chart(c, use_container_width=True)

        elif dim == "Asset Allocation":
            alloc = state_df[state_df["dimension"] == "asset_allocation"].copy()
            if not alloc.empty:
                alloc_colors = {"equity": "#4ade80", "debt": "#60a5fa", "hybrid": "#f59e0b", "passive": "#a78bfa", "others": "#94a3b8"}
                c = alt.Chart(alloc).mark_bar().encode(
                    x=alt.X("value_pct:Q", stack="normalize", title="Allocation %", axis=alt.Axis(format="%")),
                    y=alt.Y("state:N", sort=alt.EncodingSortField(field="value_pct", op="sum", order="descending"), title=""),
                    color=alt.Color("sub_dimension:N", title="Category",
                                    scale=alt.Scale(domain=list(alloc_colors.keys()), range=list(alloc_colors.values()))),
                    tooltip=[alt.Tooltip("state:N"), alt.Tooltip("sub_dimension:N", title="Category"), alt.Tooltip("value_pct:Q", format=".1f", title="%")],
                ).properties(height=len(alloc["state"].unique()) * 20 + 50)
                st.altair_chart(c, use_container_width=True)

        elif dim == "Age Groups":
            age = state_df[state_df["dimension"] == "age_group"].copy()
            if not age.empty:
                age_colors = {"below_25": "#4ade80", "25_to_44": "#60a5fa", "45_to_58": "#f59e0b", "above_58": "#f472b6", "not_specified": "#94a3b8"}
                c = alt.Chart(age).mark_bar().encode(
                    x=alt.X("value_pct:Q", stack="normalize", title="Age Distribution %", axis=alt.Axis(format="%")),
                    y=alt.Y("state:N", sort=alt.EncodingSortField(field="value_pct", op="sum", order="descending"), title=""),
                    color=alt.Color("sub_dimension:N", title="Age Group",
                                    scale=alt.Scale(domain=list(age_colors.keys()), range=list(age_colors.values()))),
                    tooltip=[alt.Tooltip("state:N"), alt.Tooltip("sub_dimension:N", title="Age Group"), alt.Tooltip("value_pct:Q", format=".1f", title="%")],
                ).properties(height=len(age["state"].unique()) * 20 + 50)
                st.altair_chart(c, use_container_width=True)


# =====================================================================
# PAGE: SCHEME PORTFOLIOS
# =====================================================================

elif page == "Scheme Portfolios":
    st.title("Scheme Portfolios")
    st.caption("Holdings of individual mutual fund schemes — Feb 2026")

    # Load scheme master
    @st.cache_data(ttl=3600)
    def load_scheme_master():
        supabase = get_supabase()
        result = supabase.table("scheme_master").select("*").eq("is_pilot", True).order("amc_short").execute()
        return pd.DataFrame(result.data)

    @st.cache_data(ttl=3600)
    def load_holdings(scheme_code):
        supabase = get_supabase()
        result = (
            supabase.table("scheme_holdings")
            .select("*")
            .eq("scheme_code", scheme_code)
            .order("pct_to_nav", desc=True)
            .execute()
        )
        hdf = pd.DataFrame(result.data)
        for col in ["market_value_cr", "pct_to_nav", "quantity"]:
            if col in hdf.columns:
                hdf[col] = pd.to_numeric(hdf[col], errors="coerce")
        return hdf

    schemes = load_scheme_master()

    if schemes.empty:
        st.warning("No scheme data available.")
    else:
        CAP_COLORS_ST = {"Large Cap": "#4ade80", "Mid Cap": "#60a5fa", "Small Cap": "#f59e0b"}

        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            amcs = ["All"] + sorted(schemes["amc_short"].dropna().unique().tolist())
            sel_amc = st.selectbox("AMC", amcs)
        filt = schemes if sel_amc == "All" else schemes[schemes["amc_short"] == sel_amc]
        with col2:
            cats = ["All"] + sorted(filt["category"].dropna().unique().tolist())
            sel_cat = st.selectbox("Category", cats)
        if sel_cat != "All":
            filt = filt[filt["category"] == sel_cat]
        with col3:
            scheme_opts = filt[["scheme_code", "scheme_name_short", "amc_short"]].drop_duplicates()
            scheme_opts["label"] = scheme_opts["scheme_name_short"] + " (" + scheme_opts["amc_short"] + ")"
            sel_label = st.selectbox("Scheme", scheme_opts["label"].tolist())

        if sel_label:
            sel_row = scheme_opts[scheme_opts["label"] == sel_label].iloc[0]
            sel_code = int(sel_row["scheme_code"])
            scheme_info = schemes[schemes["scheme_code"] == sel_code].iloc[0]

            # Scheme header
            nav_val = scheme_info.get("latest_nav")
            nav_str = f"₹{float(nav_val):,.2f}" if pd.notna(nav_val) else "—"
            st.caption(f"**{scheme_info['amc_name']}** · {scheme_info['category']} · NAV: {nav_str}")

            hdf = load_holdings(sel_code)

            if hdf.empty:
                st.info("No holdings data for this scheme.")
            else:
                # Summary metrics
                mc1, mc2, mc3, mc4 = st.columns(4)
                eq_pct = hdf[hdf["security_type"] == "Equity"]["pct_to_nav"].sum()
                total_val = hdf["market_value_cr"].sum()
                top_sector = hdf[hdf["security_type"] == "Equity"].groupby("industry_sector")["pct_to_nav"].sum().idxmax() if not hdf[hdf["security_type"] == "Equity"].empty else "—"
                mc1.metric("Holdings", str(len(hdf)))
                mc2.metric("Equity %", f"{eq_pct:.1f}%")
                mc3.metric("AUM", fmt_cr(total_val))
                mc4.metric("Top Sector", top_sector)

                # Market cap breakdown
                eq_only = hdf[hdf["security_type"] == "Equity"].copy()
                if not eq_only.empty:
                    cap_grp = eq_only.groupby("market_cap_class")["pct_to_nav"].sum().reset_index()
                    cap_grp.columns = ["Market Cap", "% to NAV"]
                    cap_grp = cap_grp.sort_values("% to NAV", ascending=False)

                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown("**Market Cap Breakdown**")
                        cap_chart = alt.Chart(cap_grp).mark_bar(cornerRadiusEnd=4).encode(
                            x=alt.X("% to NAV:Q", title="% to NAV"),
                            y=alt.Y("Market Cap:N", sort="-x", title=""),
                            color=alt.Color("Market Cap:N", scale=alt.Scale(
                                domain=list(CAP_COLORS_ST.keys()),
                                range=list(CAP_COLORS_ST.values())
                            ), legend=None),
                            tooltip=["Market Cap", alt.Tooltip("% to NAV:Q", format=".1f")]
                        ).properties(height=120)
                        st.altair_chart(cap_chart, use_container_width=True)

                    with col_b:
                        st.markdown("**Top Sectors**")
                        sec_grp = eq_only.groupby("industry_sector")["pct_to_nav"].sum().reset_index()
                        sec_grp.columns = ["Sector", "% to NAV"]
                        sec_grp = sec_grp.sort_values("% to NAV", ascending=False).head(8)
                        sec_chart = alt.Chart(sec_grp).mark_bar(cornerRadiusEnd=4, color="#4ade80").encode(
                            x=alt.X("% to NAV:Q", title="% to NAV"),
                            y=alt.Y("Sector:N", sort="-x", title=""),
                            tooltip=["Sector", alt.Tooltip("% to NAV:Q", format=".1f")]
                        ).properties(height=200)
                        st.altair_chart(sec_chart, use_container_width=True)

                # Holdings table
                st.markdown("**Holdings**")
                type_filter = st.multiselect(
                    "Filter by type",
                    hdf["security_type"].unique().tolist(),
                    default=hdf["security_type"].unique().tolist()
                )
                display_df = hdf[hdf["security_type"].isin(type_filter)][
                    ["security_name", "security_type", "industry_sector", "market_cap_class", "pct_to_nav", "market_value_cr"]
                ].copy()
                display_df.columns = ["Security", "Type", "Sector", "Market Cap", "% NAV", "Value (Cr)"]
                display_df["% NAV"] = display_df["% NAV"].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "—")
                display_df["Value (Cr)"] = display_df["Value (Cr)"].apply(lambda x: fmt_cr(x) if pd.notna(x) else "—")
                st.dataframe(display_df, use_container_width=True, hide_index=True, height=500)

                # Download
                dl_df = hdf[["security_name", "isin", "security_type", "industry_sector", "market_cap_class", "quantity", "market_value_cr", "pct_to_nav"]].copy()
                st.download_button(
                    "Download CSV",
                    dl_df.to_csv(index=False),
                    file_name=f"portfolio_{sel_code}_feb2026.csv",
                    mime="text/csv"
                )


# =====================================================================
# PAGE: DATA EXPLORER
# =====================================================================

elif page == "Data Explorer":
    st.title("Data Explorer")
    st.caption("Browse and download raw data")

    dataset = st.selectbox("Select Dataset", ["Monthly AUM & Flows", "QAAUM by Fund House", "Industry Metrics", "State Data"])

    if dataset == "Monthly AUM & Flows":
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

        cols = ["category", "section", "group", "aum_cr", "net_flow_cr", "funds_mobilized_cr", "redemption_cr", "num_folios", "num_schemes"]
        filtered = filtered[cols].sort_values("aum_cr", ascending=False)
        filtered.columns = ["Category", "Section", "Group", "AUM (Cr)", "Net Flow (Cr)", "Gross Sales (Cr)", "Redemptions (Cr)", "Folios", "Schemes"]
        st.dataframe(filtered, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", filtered.to_csv(index=False),
                           file_name=f"mf_monthly_{pd.Timestamp(selected_month).strftime('%Y_%m')}.csv", mime="text/csv")

    elif dataset == "QAAUM by Fund House":
        qdf = load_qaaum()
        periods = sorted(qdf["period_start"].unique(), reverse=True)
        sel_period = st.selectbox("Period", periods, format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"))
        filtered = qdf[qdf["period_start"] == sel_period][["fund_house", "aaum_total_cr", "aaum_excl_cr", "aaum_fof_cr"]].sort_values("aaum_total_cr", ascending=False)
        filtered.columns = ["Fund House", "Total AAUM (Cr)", "Excl FoF (Cr)", "FoF (Cr)"]
        st.dataframe(filtered, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", filtered.to_csv(index=False),
                           file_name=f"qaaum_{pd.Timestamp(sel_period).strftime('%Y_%m')}.csv", mime="text/csv")

    elif dataset == "Industry Metrics":
        mdf = load_metrics()
        cats = sorted(mdf["metric_category"].unique())
        sel_cat = st.selectbox("Category", ["All"] + cats)
        if sel_cat != "All":
            mdf = mdf[mdf["metric_category"] == sel_cat]
        display = mdf[["metric_name", "metric_category", "period_date", "value", "unit", "segment"]].sort_values(["metric_name", "period_date"], ascending=[True, False])
        display.columns = ["Metric", "Category", "Date", "Value", "Unit", "Segment"]
        st.dataframe(display, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", display.to_csv(index=False), file_name="mf_industry_metrics.csv", mime="text/csv")

    elif dataset == "State Data":
        sdf = load_state_data()
        dims = sorted(sdf["dimension"].unique())
        sel_dim = st.selectbox("Dimension", ["All"] + dims)
        if sel_dim != "All":
            sdf = sdf[sdf["dimension"] == sel_dim]
        display = sdf[["state", "dimension", "sub_dimension", "value_pct", "source_report"]].sort_values(["state", "dimension"])
        display.columns = ["State", "Dimension", "Sub-dimension", "Value %", "Source"]
        st.dataframe(display, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", display.to_csv(index=False), file_name="mf_state_data.csv", mime="text/csv")
