import pandas as pd
import streamlit as st
import altair as alt


def render_past_due_bins(past_due_df: pd.DataFrame):
    st.divider()
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
