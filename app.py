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
def load_qaaum_schemes():
    data = fetch_all("qaaum_schemewise", "period_start")
    df = pd.DataFrame(data)
    df["period_start"] = pd.to_datetime(df["period_start"])
    for col in ["aaum_excl_cr", "aaum_fof_cr", "aaum_total_cr"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=3600)
def load_scheme_categories():
    """Load scheme_code → category mapping from scheme_master."""
    supabase = get_supabase()
    all_data = []
    offset = 0
    page_size = 1000
    while True:
        result = supabase.table("scheme_master").select("scheme_code,category,asset_class").range(offset, offset + page_size - 1).execute()
        all_data.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size
    return pd.DataFrame(all_data)


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
    return f"₹{val:,.0f} Cr"


def fmt_cr_short(val):
    if pd.isna(val):
        return "—"
    if abs(val) >= 100000:
        return f"{val / 100000:,.1f}L Cr"
    return f"{val:,.0f} Cr"


def fmt_num(val):
    if pd.isna(val):
        return "—"
    if abs(val) >= 10000000:
        return f"{val / 10000000:,.2f} Cr"
    if abs(val) >= 100000:
        return f"{val / 100000:,.1f}L"
    return f"{val:,.0f}"


def smart_round(val):
    """Value-dependent rounding: >30→0dp, 10-30→1dp, 0-10→2dp."""
    if pd.isna(val):
        return "—"
    a = abs(val)
    if a > 30:
        return f"{val:,.0f}"
    elif a >= 10:
        return f"{val:,.1f}"
    else:
        return f"{val:,.2f}"


def smart_round_pct(val, signed=False):
    """Smart-rounded percentage with % symbol."""
    if pd.isna(val):
        return "—"
    a = abs(val)
    if a > 30:
        dp = 0
    elif a >= 10:
        dp = 1
    else:
        dp = 2
    if signed:
        return f"{val:+.{dp}f}%"
    return f"{val:.{dp}f}%"


def fmt_pct(val):
    if pd.isna(val):
        return "—"
    return smart_round_pct(val, signed=True)


def pct_change(new, old):
    if pd.isna(new) or pd.isna(old) or old == 0:
        return None
    return ((new / old) - 1) * 100


def y_axis_lakhs_cr(title=""):
    return alt.Axis(
        title=title,
        format="~s",
        labelExpr="datum.value >= 100000 ? format(datum.value / 100000, '.0f') + 'L Cr' : format(datum.value, ',.0f') + ' Cr'"
    )


def bar_labels(chart, field, fmt=",.0f", color="#ffffff", font_size=11):
    """Add data labels to a bar chart. Returns a layered chart."""
    return chart + chart.mark_text(
        align="center", dy=-10, fontSize=font_size, color=color,
    ).encode(text=alt.Text(f"{field}:Q", format=fmt))


def hbar_labels(chart, field, fmt=",.0f", color="#ffffff", font_size=11):
    """Add data labels to a horizontal bar chart."""
    return chart + chart.mark_text(
        align="left", dx=4, fontSize=font_size, color=color,
    ).encode(text=alt.Text(f"{field}:Q", format=fmt))


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

# Grouped page list with section dividers
PAGE_LIST = [
    "---Monthly Fact Sheet---",
    "Industry Pulse",
    "Flows",
    "Categories",
    "---QAUM---",
    "Market Share",
    "---Classified AAUM---",
    "MAAUM",
    "---Tools---",
    "Scheme Portfolios",
    "Data Explorer",
]

# Render as selectbox with section headers (Streamlit doesn't support grouped radio)
# Use a single selectbox for clean single-selection
actual_pages = [p for p in PAGE_LIST if not p.startswith("---")]

# Build sidebar navigation manually with section headers and buttons
if "_active_page" not in st.session_state:
    st.session_state["_active_page"] = "Industry Pulse"

for item in PAGE_LIST:
    if item.startswith("---"):
        section = item.strip("-")
        st.sidebar.markdown(f"**{section}**")
    else:
        is_active = st.session_state["_active_page"] == item
        if st.sidebar.button(
            f"{'● ' if is_active else '○ '}{item}",
            key=f"nav_{item}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state["_active_page"] = item
            st.rerun()

page = st.session_state["_active_page"]

# --- Load core data ---

df = load_monthly()
latest_month = df["report_month"].max()
prev_month = latest_month - pd.DateOffset(months=1)
year_ago = latest_month - pd.DateOffset(months=12)

# --- Shared group filter for Monthly Fact Sheet pages ---

MONTHLY_PAGES = {"Industry Pulse", "Flows", "Categories"}

if page in MONTHLY_PAGES:
    if "_group_filter" not in st.session_state:
        st.session_state["_group_filter"] = "All"
    group_filter = st.radio(
        "Filter by group", ["All"] + GROUPS, horizontal=True,
        key="_group_filter",
    )
else:
    group_filter = "All"


# =====================================================================
# PAGE: INDUSTRY PULSE
# =====================================================================

if page == "Industry Pulse":
    st.title("Industry Pulse")
    st.caption(f"Data as of {latest_month.strftime('%B %Y')}")

    gt = df[(df["report_month"] == latest_month) & (df["category"] == "Grand Total")]
    gt_prev = df[(df["report_month"] == prev_month) & (df["category"] == "Grand Total")]
    gt_yoy = df[(df["report_month"] == year_ago) & (df["category"] == "Grand Total")]

    # Equity-oriented flows
    equity_latest = df[
        (df["report_month"] == latest_month) & (df["section"] == "Open Ended") & (df["group"] == "Equity")
    ]["net_flow_cr"].sum()

    if not gt.empty:
        r = gt.iloc[0]
        rp = gt_prev.iloc[0] if not gt_prev.empty else None
        ry = gt_yoy.iloc[0] if not gt_yoy.empty else None

        mom_pct = pct_change(r['aum_cr'], rp['aum_cr']) if rp is not None else None
        yoy_pct = pct_change(r['aum_cr'], ry['aum_cr']) if ry is not None else None

        # KPI row
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total AUM", fmt_cr(r["aum_cr"]),
                   delta=f"{mom_pct:.1f}% MoM" if mom_pct is not None else None)
        c2.metric("YoY Growth", f"{yoy_pct:.1f}%" if yoy_pct is not None else "—")
        c3.metric("Net Flows", fmt_cr(r["net_flow_cr"]))
        c4.metric("Equity Flows", fmt_cr(equity_latest))

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Folios", fmt_num(r["num_folios"]),
                   delta=f"{fmt_num(r['num_folios'] - rp['num_folios'])} new" if rp is not None and not pd.isna(rp['num_folios']) else None)
        c6.metric("Schemes", f"{int(r['num_schemes']):,}" if not pd.isna(r["num_schemes"]) else "—")

    # AUM trend — uses shared group filter
    st.subheader("AUM Trend")

    if group_filter == "All":
        aum_trend = (
            df[df["category"] == "Grand Total"]
            .sort_values("report_month")[["report_month", "aum_cr"]]
            .rename(columns={"report_month": "Month", "aum_cr": "AUM"})
        )
    else:
        aum_trend = (
            df[(df["section"] == "Open Ended") & (df["group"] == group_filter)]
            .groupby("report_month")["aum_cr"].sum().reset_index()
            .sort_values("report_month")
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
    # Add total row
    total_row = pd.DataFrame([{
        "category": "Total",
        "aum_cr": group_latest["aum_cr"].sum(),
        "share": 100.0,
        "net_flow_cr": group_latest["net_flow_cr"].sum(),
        "yoy_growth": pct_change(group_latest["aum_cr"].sum(), group_latest["aum_yoy"].sum()) if "aum_yoy" in group_latest.columns else None,
        "num_folios": group_latest["num_folios"].sum(),
    }])
    display = pd.concat([display, total_row[["category", "aum_cr", "share", "net_flow_cr", "yoy_growth", "num_folios"]]], ignore_index=True)
    display.columns = ["Group", "AUM (Cr)", "Share %", "Net Flow (Cr)", "YoY Growth %", "Folios"]
    st.dataframe(
        display.style.format({
            "AUM (Cr)": "{:,.0f}",
            "Share %": lambda v: smart_round_pct(v),
            "Net Flow (Cr)": "{:,.0f}",
            "YoY Growth %": lambda v: smart_round_pct(v, signed=True),
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
    flow_groups = [group_filter] if group_filter != "All" else GROUPS
    flow_raw = df[
        (df["report_month"] > cutoff) & (df["section"] == "Open Ended") & (df["group"].isin(flow_groups))
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
        (df["report_month"] == latest_month) & (df["section"] == "Open Ended") & (df["group"].isin(flow_groups))
    ]
    latest_flow = latest_flow_raw.groupby("group").agg(
        funds_mobilized_cr=("funds_mobilized_cr", "sum"),
        redemption_cr=("redemption_cr", "sum"),
        net_flow_cr=("net_flow_cr", "sum"),
    ).reset_index().rename(columns={"group": "category"})
    latest_flow["redemption_ratio"] = (latest_flow["redemption_cr"] / latest_flow["funds_mobilized_cr"] * 100).round(1)
    latest_flow = latest_flow.sort_values("net_flow_cr", ascending=False)
    # Add total row
    total_gross = latest_flow["funds_mobilized_cr"].sum()
    total_redem = latest_flow["redemption_cr"].sum()
    total_net = latest_flow["net_flow_cr"].sum()
    total_ratio = (total_redem / total_gross * 100) if total_gross > 0 else 0
    total_row = pd.DataFrame([{"category": "Total", "funds_mobilized_cr": total_gross, "redemption_cr": total_redem, "net_flow_cr": total_net, "redemption_ratio": total_ratio}])
    latest_flow = pd.concat([latest_flow, total_row], ignore_index=True)
    latest_flow.columns = ["Group", "Gross Sales (Cr)", "Redemptions (Cr)", "Net Flow (Cr)", "Redemption Ratio %"]
    st.dataframe(
        latest_flow.style.format({
            "Gross Sales (Cr)": "{:,.0f}",
            "Redemptions (Cr)": "{:,.0f}",
            "Net Flow (Cr)": "{:,.0f}",
            "Redemption Ratio %": lambda v: smart_round_pct(v),
        }),
        use_container_width=True, hide_index=True,
    )

    # Category-level flow momentum — top gainers and losers
    st.subheader("Category Flow Momentum — Top Gainers & Losers")
    cat_flows = df[
        (df["report_month"] == latest_month)
        & (df["section"] == "Open Ended")
        & (df["group"].isin(flow_groups))
        & (~df["category"].isin(GROUPS + ["Grand Total", "Total A-Open ended Schemes"]))
    ][["category", "net_flow_cr", "aum_cr"]].copy()
    cat_flows["flow_to_aum"] = (cat_flows["net_flow_cr"] / cat_flows["aum_cr"] * 100).round(2)
    cat_flows = cat_flows.sort_values("net_flow_cr", ascending=False)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Top 5 Inflows**")
        top5 = cat_flows.head(5)[["category", "net_flow_cr", "flow_to_aum"]].copy()
        top5.columns = ["Category", "Net Flow (Cr)", "Flow/AUM %"]
        st.dataframe(top5.style.format({"Net Flow (Cr)": "{:,.0f}", "Flow/AUM %": lambda v: smart_round_pct(v)}),
                     use_container_width=True, hide_index=True)
    with col2:
        st.markdown("**Top 5 Outflows**")
        bot5 = cat_flows.tail(5).sort_values("net_flow_cr")[["category", "net_flow_cr", "flow_to_aum"]].copy()
        bot5.columns = ["Category", "Net Flow (Cr)", "Flow/AUM %"]
        st.dataframe(bot5.style.format({"Net Flow (Cr)": "{:,.0f}", "Flow/AUM %": lambda v: smart_round_pct(v)}),
                     use_container_width=True, hide_index=True)


# =====================================================================
# PAGE: CATEGORIES
# =====================================================================

elif page == "Categories":
    st.title("Category Deep Dive")
    st.caption(f"Data as of {latest_month.strftime('%B %Y')}")

    default_idx = GROUPS.index(group_filter) if group_filter in GROUPS else 0
    selected_group = st.selectbox("Select Group", GROUPS, index=default_idx)

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
        # Add total row
        total_yoy = pct_change(cat_df["aum_cr"].sum(), cat_df["aum_yoy"].sum()) if "aum_yoy" in cat_df.columns else None
        total_cat = pd.DataFrame([{
            "category": "Total", "aum_cr": cat_df["aum_cr"].sum(), "share": 100.0,
            "net_flow_cr": cat_df["net_flow_cr"].sum(), "yoy": total_yoy,
            "num_folios": cat_df["num_folios"].sum(), "num_schemes": cat_df["num_schemes"].sum(),
        }])
        display = pd.concat([display, total_cat], ignore_index=True)
        display.columns = ["Category", "AUM (Cr)", "Share %", "Net Flow (Cr)", "YoY %", "Folios", "Schemes"]
        st.dataframe(
            display.style.format({
                "AUM (Cr)": "{:,.0f}",
                "Share %": lambda v: smart_round_pct(v),
                "Net Flow (Cr)": "{:,.0f}",
                "YoY %": lambda v: smart_round_pct(v, signed=True),
                "Folios": "{:,.0f}", "Schemes": "{:,.0f}",
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

    # Bar chart with data labels
    top["label"] = top["aaum_total_cr"].apply(lambda v: fmt_cr_short(v))
    bar = alt.Chart(top).mark_bar(color="#4ade80").encode(
        x=alt.X("aaum_total_cr:Q", axis=y_axis_lakhs_cr("AAUM"), title="AAUM"),
        y=alt.Y("fund_house:N", sort="-x", title=""),
        tooltip=[
            alt.Tooltip("fund_house:N", title="Fund House"),
            alt.Tooltip("aaum_total_cr:Q", format=",.0f", title="AAUM (Cr)"),
            alt.Tooltip("share:Q", format=".2f", title="Market Share %"),
        ],
    ).properties(height=top_n * 28 + 50)
    bar_text = bar.mark_text(align="left", dx=4, fontSize=11, color="#ffffff").encode(
        text="label:N",
    )
    st.altair_chart(bar + bar_text, use_container_width=True)

    # Table
    display_q = top[["fund_house", "aaum_total_cr", "share", "share_change"]].copy()
    # Add total row for top N
    total_row_q = pd.DataFrame([{
        "fund_house": f"Total (Top {top_n})",
        "aaum_total_cr": top["aaum_total_cr"].sum(),
        "share": top["share"].sum(),
        "share_change": top["share_change"].sum() if "share_change" in top.columns else 0,
    }])
    display_q = pd.concat([display_q, total_row_q], ignore_index=True)
    display_q.columns = ["Fund House", "AAUM (Cr)", "Share %", "Change (bps)"]
    display_q["Change (bps)"] = (display_q["Change (bps)"] * 100).round(0)
    st.dataframe(
        display_q.style.format({
            "AAUM (Cr)": "{:,.0f}",
            "Share %": lambda v: smart_round_pct(v),
            "Change (bps)": "{:+.0f}",
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

    # --- Scheme-level Data ---
    st.divider()
    st.subheader("Scheme-level QAUM")

    sdf = load_qaaum_schemes()
    if not sdf.empty:
        s_latest = sdf["period_start"].max()
        st.caption(f"Scheme data as of {s_latest.strftime('%B %Y')} quarter")

        stab1, stab2, stab3 = st.tabs(["Top Schemes", "AMC × Scheme Drill-down", "Category × AMC"])

        with stab1:
            top_s_n = st.slider("Top schemes", 10, 50, 25, key="top_schemes_n")
            s_latest_data = sdf[sdf["period_start"] == s_latest].sort_values("aaum_total_cr", ascending=False)
            top_schemes = s_latest_data.head(top_s_n).copy()
            top_schemes["display_name"] = top_schemes["scheme_name"].str[:60]

            top_schemes["label"] = top_schemes["aaum_total_cr"].apply(lambda v: fmt_cr_short(v))
            s_bar = alt.Chart(top_schemes).mark_bar(color="#60a5fa").encode(
                x=alt.X("aaum_total_cr:Q", axis=y_axis_lakhs_cr("AAUM"), title="AAUM (Cr)"),
                y=alt.Y("display_name:N", sort="-x", title=""),
                color=alt.Color("mf_name:N", title="AMC", legend=None),
                tooltip=[
                    alt.Tooltip("scheme_name:N", title="Scheme"),
                    alt.Tooltip("mf_name:N", title="AMC"),
                    alt.Tooltip("aaum_total_cr:Q", format=",.0f", title="AAUM (Cr)"),
                ],
            ).properties(height=top_s_n * 22 + 50)
            s_text = s_bar.mark_text(align="left", dx=4, fontSize=10, color="#ffffff").encode(text="label:N")
            st.altair_chart(s_bar + s_text, use_container_width=True)

            # Table
            s_table = top_schemes[["scheme_name", "mf_name", "aaum_total_cr"]].copy()
            s_total = s_latest_data["aaum_total_cr"].sum()
            s_table["share"] = (s_table["aaum_total_cr"] / s_total * 100).round(2)
            # Add total row
            s_total_row = pd.DataFrame([{
                "scheme_name": f"Total (Top {top_s_n})", "mf_name": "",
                "aaum_total_cr": s_table["aaum_total_cr"].sum(),
                "share": s_table["share"].sum(),
            }])
            s_table = pd.concat([s_table, s_total_row], ignore_index=True)
            s_table.columns = ["Scheme", "AMC", "AAUM (Cr)", "Share %"]
            st.dataframe(
                s_table.style.format({"AAUM (Cr)": "{:,.0f}", "Share %": lambda v: smart_round_pct(v)}),
                use_container_width=True, hide_index=True,
            )

        with stab2:
            # Select an AMC to drill into its schemes
            amc_list_s = sorted(sdf[sdf["period_start"] == s_latest]["mf_name"].unique())
            sel_amc = st.selectbox("Select AMC", amc_list_s, key="scheme_amc_select")
            amc_schemes = (
                sdf[(sdf["period_start"] == s_latest) & (sdf["mf_name"] == sel_amc)]
                .sort_values("aaum_total_cr", ascending=False)
            )

            st.metric("Total QAUM", fmt_cr(amc_schemes["aaum_total_cr"].sum()))
            st.metric("Schemes", f"{len(amc_schemes):,}")

            # Show top schemes for this AMC
            amc_top = amc_schemes.head(20).copy()
            amc_top["display_name"] = amc_top["scheme_name"].str[:50]
            amc_top["label"] = amc_top["aaum_total_cr"].apply(lambda v: fmt_cr_short(v))
            amc_bar = alt.Chart(amc_top).mark_bar(color="#4ade80").encode(
                x=alt.X("aaum_total_cr:Q", title="AAUM (Cr)"),
                y=alt.Y("display_name:N", sort="-x", title=""),
                tooltip=[
                    alt.Tooltip("scheme_name:N", title="Scheme"),
                    alt.Tooltip("aaum_total_cr:Q", format=",.0f", title="AAUM (Cr)"),
                ],
            ).properties(height=20 * 22 + 50)
            amc_text = amc_bar.mark_text(align="left", dx=4, fontSize=10, color="#ffffff").encode(text="label:N")
            st.altair_chart(amc_bar + amc_text, use_container_width=True)

            # Scheme trend — select specific schemes to compare over quarters
            amc_scheme_names = amc_schemes["scheme_name"].tolist()[:10]
            sel_schemes = st.multiselect("Compare schemes over time", amc_scheme_names, default=amc_scheme_names[:3], key="scheme_compare")
            if sel_schemes:
                s_trend = sdf[(sdf["mf_name"] == sel_amc) & (sdf["scheme_name"].isin(sel_schemes))].sort_values("period_start")
                s_trend["short_name"] = s_trend["scheme_name"].str[:40]
                s_trend_chart = alt.Chart(s_trend).mark_line(strokeWidth=2).encode(
                    x=alt.X("period_start:T", title=""),
                    y=alt.Y("aaum_total_cr:Q", title="AAUM (Cr)"),
                    color=alt.Color("short_name:N", title="Scheme"),
                    tooltip=[
                        alt.Tooltip("period_start:T", format="%B %Y"),
                        alt.Tooltip("scheme_name:N"),
                        alt.Tooltip("aaum_total_cr:Q", format=",.0f", title="AAUM (Cr)"),
                    ],
                ).properties(height=300)
                st.altair_chart(s_trend_chart, use_container_width=True)
        with stab3:
            # Category × AMC market share using scheme-level QAUM + scheme_master
            cat_df = load_scheme_categories()
            if not cat_df.empty:
                # Join scheme QAUM with categories
                s_latest_data = sdf[sdf["period_start"] == s_latest].copy()
                merged = s_latest_data.merge(
                    cat_df, left_on="amfi_code", right_on="scheme_code", how="left"
                )
                merged = merged.dropna(subset=["category"])

                # Asset class filter
                asset_classes = sorted(merged["asset_class"].dropna().unique())
                sel_asset = st.selectbox("Asset class", ["All"] + asset_classes, key="cat_amc_asset")
                if sel_asset != "All":
                    merged = merged[merged["asset_class"] == sel_asset]

                # Category filter
                categories = sorted(merged["category"].dropna().unique())
                sel_cat = st.selectbox("Category", categories, key="cat_amc_cat")

                cat_data = merged[merged["category"] == sel_cat]
                cat_total = cat_data["aaum_total_cr"].sum()

                if cat_total > 0:
                    # Aggregate by AMC
                    amc_agg = (
                        cat_data.groupby("mf_name")["aaum_total_cr"]
                        .sum()
                        .sort_values(ascending=False)
                        .reset_index()
                    )
                    amc_agg["share"] = (amc_agg["aaum_total_cr"] / cat_total * 100).round(2)

                    st.metric(f"{sel_cat} — Total QAUM", fmt_cr(cat_total))
                    st.caption(f"{len(amc_agg)} fund houses")

                    # Bar chart — top 15 with labels
                    top_amc = amc_agg.head(15).copy()
                    top_amc["label"] = top_amc["aaum_total_cr"].apply(lambda v: fmt_cr_short(v))
                    cat_bar = alt.Chart(top_amc).mark_bar(color="#4ade80").encode(
                        x=alt.X("aaum_total_cr:Q", axis=y_axis_lakhs_cr("AAUM"), title="AAUM (Cr)"),
                        y=alt.Y("mf_name:N", sort="-x", title=""),
                        tooltip=[
                            alt.Tooltip("mf_name:N", title="AMC"),
                            alt.Tooltip("aaum_total_cr:Q", format=",.0f", title="AAUM (Cr)"),
                            alt.Tooltip("share:Q", format=".2f", title="Market Share %"),
                        ],
                    ).properties(height=15 * 28 + 50)
                    cat_text = cat_bar.mark_text(align="left", dx=4, fontSize=11, color="#ffffff").encode(text="label:N")
                    st.altair_chart(cat_bar + cat_text, use_container_width=True)

                    # Table with total
                    display_amc = amc_agg[["mf_name", "aaum_total_cr", "share"]].copy()
                    amc_total_row = pd.DataFrame([{
                        "mf_name": "Total", "aaum_total_cr": amc_agg["aaum_total_cr"].sum(),
                        "share": amc_agg["share"].sum(),
                    }])
                    display_amc = pd.concat([display_amc, amc_total_row], ignore_index=True)
                    display_amc.columns = ["AMC", "AAUM (Cr)", "Market Share %"]
                    st.dataframe(
                        display_amc.style.format({"AAUM (Cr)": "{:,.0f}", "Market Share %": lambda v: smart_round_pct(v)}),
                        use_container_width=True, hide_index=True,
                    )
                else:
                    st.info(f"No data for {sel_cat}")
            else:
                st.info("Scheme category data not available.")

    else:
        st.info("Scheme-level QAUM data not yet loaded.")


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
                "Active%": lambda v: smart_round_pct(v), "Equity%": lambda v: smart_round_pct(v), "Debt%": lambda v: smart_round_pct(v),
                "ETF%": lambda v: smart_round_pct(v), "Individual%": lambda v: smart_round_pct(v), "B30%": lambda v: smart_round_pct(v),
                "Direct%": lambda v: smart_round_pct(v), "Assoc Dist%": lambda v: smart_round_pct(v), "Non-Assoc%": lambda v: smart_round_pct(v),
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
                "AUM (Cr)": "{:,.0f}", "Market Share%": lambda v: smart_round_pct(v),
                "AUM Growth (Cr)": "{:,.0f}", "Growth Share%": lambda v: smart_round_pct(v),
            }),
            use_container_width=True, hide_index=True,
        )

        # Horizontal bar chart — top 15
        bar_data = rank_df.head(15).copy()
        bar_data["mf_name"] = bar_data["mf_name"].str.replace(" Mutual Fund", " MF")
        bar_data["label"] = bar_data["aum"].apply(lambda v: fmt_cr_short(v))
        bar = alt.Chart(bar_data).mark_bar(color="#4ade80").encode(
            x=alt.X("aum:Q", axis=y_axis_lakhs_cr("AUM"), title="AUM (Cr)"),
            y=alt.Y("mf_name:N", sort="-x", title=""),
            tooltip=[
                alt.Tooltip("mf_name:N", title="AMC"),
                alt.Tooltip("aum:Q", format=",.0f", title="AUM (Cr)"),
                alt.Tooltip("share:Q", format=".2f", title="Share %"),
            ],
        ).properties(height=15 * 28 + 50)
        bar_text = bar.mark_text(align="left", dx=4, fontSize=11, color="#ffffff").encode(text="label:N")
        st.altair_chart(bar + bar_text, use_container_width=True)

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
            "Market Share%": lambda v: smart_round_pct(v), "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": lambda v: smart_round_pct(v),
        }), use_container_width=True, hide_index=True)

        # Asset Class
        st.markdown("**Asset Class Breakdown**")
        asset_groups = ["Equity", "Debt", "Liquid", "Hybrid", "ETF", "FOF"]
        ac_map = {g: (lambda d, g=g: d[d["category_group"] == g]) for g in asset_groups}
        ac_df = build_asset_table("Asset Class", ac_map, sel_mf_id, asset_start, asset_end)
        ac_df = ac_df[ac_df["AMC AUM (Cr)"] > 0]
        st.dataframe(ac_df.style.format({
            "AMC AUM (Cr)": "{:,.0f}", "Industry AUM (Cr)": "{:,.0f}",
            "Market Share%": lambda v: smart_round_pct(v), "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": lambda v: smart_round_pct(v),
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
            "Market Share%": lambda v: smart_round_pct(v), "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": lambda v: smart_round_pct(v),
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
            "Market Share%": lambda v: smart_round_pct(v), "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": lambda v: smart_round_pct(v),
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
            "Market Share%": lambda v: smart_round_pct(v), "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": lambda v: smart_round_pct(v),
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
            "Market Share%": lambda v: smart_round_pct(v), "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": lambda v: smart_round_pct(v),
        }), use_container_width=True, hide_index=True)

        # 3 channels
        st.markdown("**By Distribution Channel**")
        ch_labels = {"TDP": "Direct", "TAD": "Assoc Dist", "TNAD": "Non-Assoc Dist"}
        ch_map = {v: (lambda d, ch=k: d[d["dist_channel"] == ch]) for k, v in ch_labels.items()}
        ch_df = build_asset_table("Channel", ch_map, sel_mf_id_dist, dist_start, dist_end)
        st.dataframe(ch_df.style.format({
            "AMC AUM (Cr)": "{:,.0f}", "Industry AUM (Cr)": "{:,.0f}",
            "Market Share%": lambda v: smart_round_pct(v), "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": lambda v: smart_round_pct(v),
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
            "Market Share%": lambda v: smart_round_pct(v), "AMC Growth (Cr)": "{:,.0f}",
            "Industry Growth (Cr)": "{:,.0f}", "Growth Share%": lambda v: smart_round_pct(v),
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
        fmt_dict = {c: (lambda v: smart_round_pct(v)) for c in month_cols}
        st.dataframe(
            trend_df.style.format(fmt_dict),
            use_container_width=True, hide_index=True,
        )


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
