import pandas as pd
import streamlit as st
import altair as alt
import plotly.express as px

def render_past_due_bins(past_due_df: pd.DataFrame):
    st.subheader("Past Due Aging")

    if past_due_df.empty:
        st.warning("No past-due rows under current filters.")
        return

    tmp = past_due_df.dropna(subset=["days_since_issue"]).copy()
    if tmp.empty:
        st.warning("Past-due rows have no days_since_issue.")
        return

    max_days = int(tmp["days_since_issue"].max())
    max_edge = ((max_days // 30) + 1) * 30
    edges = list(range(0, max_edge + 30, 30))
    labels = [f"{edges[i]}-{edges[i+1]-1}" for i in range(len(edges) - 1)]

    tmp["aging_bin"] = pd.cut(
        tmp["days_since_issue"],
        bins=edges,
        labels=labels,
        right=False,
        include_lowest=True,
    )

    tmp["bin_start"] = tmp["aging_bin"].astype(str).str.split("-").str[0].astype(int)

    count_by = (
        tmp.groupby(["aging_bin", "bin_start"])
        .size()
        .reset_index(name="count")
        .sort_values("bin_start")
    )

    amt_by = (
        tmp.groupby(["aging_bin", "bin_start"])["total_amount_with_taxes"]
        .sum()
        .reset_index(name="amount")
        .sort_values("bin_start")
    )

    x_order = [str(x) for x in count_by["aging_bin"].tolist()]

    left, right = st.columns(2)

    # keep exact colors/scale from your original
    with left:
        st.altair_chart(
            alt.Chart(count_by)
            .mark_bar()
            .encode(
                x=alt.X("aging_bin:N", sort=x_order),
                y="count:Q",
                color=alt.Color(
                    "bin_start:Q",
                    scale=alt.Scale(domain=[0, max_edge], range=["#2ecc71", "#f1c40f", "#e74c3c"]),
                    legend=None,
                ),
                tooltip=["aging_bin", "count"],
            )
            .properties(height=260),
            use_container_width=True,
        )

    with right:
        st.altair_chart(
            alt.Chart(amt_by)
            .mark_bar()
            .encode(
                x=alt.X("aging_bin:N", sort=x_order),
                y="amount:Q",
                color=alt.Color(
                    "bin_start:Q",
                    scale=alt.Scale(domain=[0, max_edge], range=["#2ecc71", "#f1c40f", "#e74c3c"]),
                    legend=None,
                ),
                tooltip=["aging_bin", alt.Tooltip("amount:Q", format=",.2f")],
            )
            .properties(height=260),
            use_container_width=True,
        )

def render_split_100pct_with_pie(
    df: pd.DataFrame,
    group_by: str = "vendor",  # "vendor" or "buyer"
    top_n: int = 20,
    vendor_col: str = "vendor_company_name",
    buyer_col: str = "buyer_company_name",
    past_due_col: str = "past_due",
    amount_col: str = "total_amount_with_taxes",
):
    """
    Top: Vertical bars of total unpaid amount by group (thicker bars).
    Bottom: Horizontal 100% stacked bars split by Past Due / Not Past Due.
    Assumes df already contains ONLY unpaid rows.
    """

    st.subheader(f"Unpaid by {group_by.title()}")

    if df.empty:
        st.warning("No rows under current filters.")
        return

    group_by = group_by.lower()
    if group_by not in {"vendor", "buyer"}:
        st.error('group_by must be "vendor" or "buyer".')
        return

    group_col = vendor_col if group_by == "vendor" else buyer_col

    needed = {group_col, past_due_col, amount_col}
    missing = needed - set(df.columns)
    if missing:
        st.error(f"Missing columns: {sorted(missing)}")
        return

    tmp = df.dropna(subset=[group_col, past_due_col, amount_col]).copy()
    if tmp.empty:
        st.warning("No usable rows after dropping missing values.")
        return

    # True = Past Due
    tmp["status"] = tmp[past_due_col].map({True: "Past Due", False: "Not Past Due"})

    # Robust ordering for stacks (controls bar + label alignment)
    tmp["status_order"] = tmp["status"].map({"Past Due": 0, "Not Past Due": 1})

    g = (
        tmp.groupby([group_col, "status", "status_order"], as_index=False)[amount_col]
        .sum()
        .rename(columns={group_col: "group", amount_col: "amount"})
    )

    totals = (
        g.groupby("group", as_index=False)["amount"]
        .sum()
        .rename(columns={"amount": "total"})
    )

    g = g.merge(totals, on="group", how="left")
    g["pct"] = g["amount"] / g["total"]

    # Keep only top_n groups
    top_groups = totals.sort_values("total", ascending=False).head(top_n)["group"].tolist()
    g = g[g["group"].isin(top_groups)]
    totals = totals[totals["group"].isin(top_groups)]

    order = totals.sort_values("total", ascending=False)["group"].tolist()

    # ---------------- TOP: VERTICAL BARS (TOTALS) ----------------
    # Thicker bars + chart can grow in height (no scroll container here)
    totals_row_height = 34
    totals_height = max(len(order) * totals_row_height, 420)

    totals_chart = (
        alt.Chart(totals)
        .mark_bar(size=40)  # thicker than stacked chart
        .encode(
            x=alt.X("group:N", sort=order, title=group_by.title()),
            y=alt.Y("total:Q", title="Total unpaid amount"),
            tooltip=[
                alt.Tooltip("group:N", title=group_by.title()),
                alt.Tooltip("total:Q", title="Total unpaid", format=",.2f"),
            ],
        )
        .properties(
            height=totals_height,
            title=f"Total Unpaid Amount by {group_by.title()}",
        )
    )

    st.altair_chart(totals_chart, use_container_width=True)

    # ---------------- BOTTOM: HORIZONTAL 100% STACKED BARS ----------------
    # Let it extend vertically as needed (no fixed 380); compute height from #groups
    stacked_row_height = 28
    stacked_height = max(len(order) * stacked_row_height, 380)

    color_scale = alt.Scale(
        domain=["Past Due", "Not Past Due"],
        range=["#e74c3c", "#2ecc71"],
    )

    bars = (
        alt.Chart(g)
        .mark_bar(size=18)
        .encode(
            y=alt.Y("group:N", sort=order, title=group_by.title()),
            x=alt.X(
                "pct:Q",
                stack="normalize",
                title="Share of unpaid amount",
                axis=alt.Axis(format="%"),
            ),
            color=alt.Color("status:N", scale=color_scale, title=None),
            order=alt.Order("status_order:Q", sort="ascending"),
            tooltip=[
                alt.Tooltip("group:N", title=group_by.title()),
                alt.Tooltip("status:N", title="Status"),
                alt.Tooltip("pct:Q", title="% of group", format=".0%"),
                alt.Tooltip("amount:Q", title="Amount", format=",.2f"),
                alt.Tooltip("total:Q", title="Group total", format=",.2f"),
            ],
        )
        .properties(height=stacked_height)
    )

    labels = (
        alt.Chart(g)
        .transform_filter("datum.pct >= 0.06")
        .transform_stack(
            stack="pct",
            groupby=["group"],
            sort=[alt.SortField("status_order", order="ascending")],
            as_=["x0", "x1"],
        )
        .transform_calculate(
            x_mid="(datum.x0 + datum.x1) / 2",
            label='format(datum.pct, ".0%")',
        )
        .mark_text(size=12, color="white")
        .encode(
            y=alt.Y("group:N", sort=order),
            x=alt.X("x_mid:Q"),
            text="label:N",
        )
        .properties(height=stacked_height)
    )

    st.altair_chart(bars + labels, use_container_width=True)


LIGHT_GREEN = "#C8E6C9"  # Current
LIGHT_RED = "#FFCDD2"    # Past Due


def _metrics_rollup(df_f: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a 4-row table:
      status ∈ {Current, Past Due}
      invoice_type ∈ {Regular, One Shot}
      amount = sum(total_amount_with_taxes)
      count  = number of invoices
    """
    needed = {"past_due", "invoice_type", "total_amount_with_taxes"}
    missing = needed - set(df_f.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    tmp = df_f.dropna(subset=["past_due", "invoice_type", "total_amount_with_taxes"]).copy()
    tmp["status"] = tmp["past_due"].map({True: "Past Due", False: "Current"})

    # keep only the two types you want (optional but helps avoid surprises)
    tmp = tmp[tmp["invoice_type"].isin(["Regular", "One Shot"])]

    out = (
        tmp.groupby(["status", "invoice_type"], as_index=False)
        .agg(
            amount=("total_amount_with_taxes", "sum"),
            count=("invoice_type", "size"),
        )
    )

    # ensure all 4 combos exist (so treemap doesn't disappear when empty)
    full = pd.MultiIndex.from_product(
        [["Current", "Past Due"], ["Regular", "One Shot"]],
        names=["status", "invoice_type"],
    ).to_frame(index=False)

    out = full.merge(out, on=["status", "invoice_type"], how="left").fillna({"amount": 0.0, "count": 0})
    out["count"] = out["count"].astype(int)
    out["amount"] = out["amount"].astype(float)
    return out


def render_metrics_treemap_value(df_f: pd.DataFrame, height: int = 320):
    """Treemap by $ value: Current/Past Due -> Regular/One Shot."""
    g = _metrics_rollup(df_f)

    fig = px.treemap(
        g,
        path=["status", "invoice_type"],
        values="amount",
        color="status",
        color_discrete_map={"Current": LIGHT_GREEN, "Past Due": LIGHT_RED},
    )

    # Show values on the boxes (with decimal point)
    fig.update_traces(
        texttemplate="%{value:,.2f}",
        textposition="middle center",
    )

    fig.update_layout(margin=dict(l=8, r=8, t=8, b=8), height=height)
    st.plotly_chart(fig, use_container_width=True)


def render_metrics_treemap_count(df_f: pd.DataFrame, height: int = 320):
    """Treemap by invoice count: Current/Past Due -> Regular/One Shot."""
    g = _metrics_rollup(df_f)

    fig = px.treemap(
        g,
        path=["status", "invoice_type"],
        values="count",
        color="status",
        color_discrete_map={"Current": LIGHT_GREEN, "Past Due": LIGHT_RED},
    )

    # Show values on the boxes (with decimal point)
    fig.update_traces(
        texttemplate="%{value:,.0f}",
        textposition="middle center",
    )

    fig.update_layout(margin=dict(l=8, r=8, t=8, b=8), height=height)
    st.plotly_chart(fig, use_container_width=True)

def render_invoices_by_days_since_issue_bars(
    df_f: pd.DataFrame,
    height: int = 360,
    invoice_id_col: str = "invoice_id",
    days_col: str = "days_since_issue",
    past_due_col: str = "past_due",
    amount_col: str = "total_amount_with_taxes",
):
    """
    Two bar charts (with a divider between):
      1) count of invoices by days_since_issue
      2) sum(total_amount_with_taxes) by days_since_issue
    Color rule:
      - green if days_since_issue <= 0
      - red   if days_since_issue > 0
    Includes multiselect for Current/Past Due using past_due_col.
    Uses df_f only.
    """
    needed = {invoice_id_col, days_col, past_due_col, amount_col}
    missing = needed - set(df_f.columns)
    if missing:
        st.error(f"Missing columns: {sorted(missing)}")
        return

    status_sel = st.multiselect(
        "Status",
        options=["Current", "Past Due"],
        default=["Current", "Past Due"],
        key="days_since_issue_status_sel",
    )

    tmp = df_f.dropna(subset=[days_col, past_due_col]).copy()
    if tmp.empty:
        st.warning("No rows under current filters.")
        return

    keep = []
    if "Current" in status_sel:
        keep.append(False)
    if "Past Due" in status_sel:
        keep.append(True)
    if not keep:
        return

    tmp = tmp[tmp[past_due_col].isin(keep)]
    if tmp.empty:
        st.warning("No rows under current filters.")
        return

    tmp[days_col] = pd.to_numeric(tmp[days_col], errors="coerce")
    tmp[amount_col] = pd.to_numeric(tmp[amount_col], errors="coerce")
    tmp = tmp.dropna(subset=[days_col, amount_col])
    if tmp.empty:
        st.warning("No rows under current filters.")
        return

    tmp[days_col] = tmp[days_col].astype(int)

    counts = (
        tmp.groupby(days_col, as_index=False)
           .agg(invoice_count=(invoice_id_col, "count"))
           .sort_values(days_col)
    )

    amounts = (
        tmp.groupby(days_col, as_index=False)
           .agg(amount=(amount_col, "sum"))
           .sort_values(days_col)
    )

    # shared color rule
    def _flag(x: int) -> str:
        return "Current (<=0)" if x <= 0 else "Past Due (>0)"

    counts["aging_status"] = counts[days_col].apply(_flag)
    amounts["aging_status"] = amounts[days_col].apply(_flag)

    color_scale = alt.Scale(
        domain=["Current (<=0)", "Past Due (>0)"],
        range=["#2ecc71", "#e74c3c"],
    )

       # Chart 1: count
    st.subheader("Invoice Count by Days Since Issue")

    chart_count = (
        alt.Chart(counts)
        .mark_bar()
        .encode(
            x=alt.X(f"{days_col}:O", title="Days Since Issue"),
            y=alt.Y("invoice_count:Q", title="Number of Invoices"),
            color=alt.Color("aging_status:N", scale=color_scale, legend=None),
            tooltip=[
                alt.Tooltip(f"{days_col}:O", title="Days"),
                alt.Tooltip("invoice_count:Q", title="Count"),
            ],
        )
        .properties(height=height)
    )
    st.altair_chart(chart_count, use_container_width=True)

    st.divider()

    # Chart 2: amount
    st.subheader("Total Amount by Days Since Issue")

    chart_amount = (
        alt.Chart(amounts)
        .mark_bar()
        .encode(
            x=alt.X(f"{days_col}:O", title="Days Since Issue"),
            y=alt.Y("amount:Q", title="Total Amount (With Taxes)"),
            color=alt.Color("aging_status:N", scale=color_scale, legend=None),
            tooltip=[
                alt.Tooltip(f"{days_col}:O", title="Days"),
                alt.Tooltip("amount:Q", title="Amount", format=",.2f"),
            ],
        )
        .properties(height=height)
    )
    st.altair_chart(chart_amount, use_container_width=True)
