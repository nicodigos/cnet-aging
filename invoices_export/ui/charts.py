import pandas as pd
import streamlit as st
import altair as alt


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
