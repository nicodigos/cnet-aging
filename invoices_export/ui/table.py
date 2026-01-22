import streamlit as st
import pandas as pd


def render_past_due_table(df_f: pd.DataFrame):
    st.divider()
    st.subheader("Past Due Table")

    table_df = df_f[df_f["past_due"]].copy()

    cols = [
        "invoice_id",
        "issue_date",
        "invoice_type",
        "buyer_company_name",
        "vendor_company_name",
        "payment_status",
        "days_since_issue",
        "total_amount_with_taxes",
        "work_description",
    ]
    cols = [c for c in cols if c in table_df.columns]
    table_df = table_df[cols]

    style = table_df.style
    if "days_since_issue" in table_df.columns:
        style = style.background_gradient(subset=["days_since_issue"], cmap="Reds")
    if "total_amount_with_taxes" in table_df.columns:
        style = style.background_gradient(subset=["total_amount_with_taxes"], cmap="Greens")

    st.dataframe(style, use_container_width=True, height=650)
