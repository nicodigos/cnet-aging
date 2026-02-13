import streamlit as st
import pandas as pd


def render_past_due_table(table_df: pd.DataFrame):
    st.divider()
    st.subheader("Unpaid Table")

    cols = [
        "invoice_id",
        "issue_date",
        "invoice_type",
        "past_due",
        "buyer_company_name",
        "vendor_company_name",
        "payment_status",
        "days_since_issue",
        "total_amount_with_taxes",
        "work_description",
    ]
    cols = [c for c in cols if c in table_df.columns]
    table_df = table_df[cols]

    if "past_due" in table_df.columns:
        table_df["past_due"] = table_df["past_due"].map(
            {True: "Past Due", False: "Current"}
        )

    def color_past_due(val):
        if pd.isna(val):
            return ""
        if val == "Past Due":
            return "background-color: #c62828; color: white;"
        else:  # "No"
            return "background-color: #2e7d32; color: white;"

    style = table_df.style

    if "past_due" in table_df.columns:
        style = style.applymap(color_past_due, subset=["past_due"])

    if "days_since_issue" in table_df.columns:
        style = style.background_gradient(subset=["days_since_issue"], cmap="Reds")

    if "total_amount_with_taxes" in table_df.columns:
        style = style.background_gradient(subset=["total_amount_with_taxes"], cmap="Greens")

    st.dataframe(style, use_container_width=True, height=650, hide_index=True)
