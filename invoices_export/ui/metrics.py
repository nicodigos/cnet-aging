import pandas as pd
import streamlit as st


def render_metrics(df_f: pd.DataFrame):
    current_df = df_f[~df_f["past_due"]]
    past_due_df = df_f[df_f["past_due"]]

    def sum_amt(x: pd.DataFrame) -> float:
        return float(x["total_amount_with_taxes"].sum()) if not x.empty else 0.0

    def sum_amt_type(x: pd.DataFrame, t: str) -> float:
        if x.empty:
            return 0.0
        return float(x.loc[x["invoice_type"] == t, "total_amount_with_taxes"].sum())

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Current ($)", f"{sum_amt(current_df):,.2f}")
    c2.metric("Past due ($)", f"{sum_amt(past_due_df):,.2f}")
    c3.metric("Current Regular ($)", f"{sum_amt_type(current_df, 'Regular'):,.2f}")
    c4.metric("Current One Shot ($)", f"{sum_amt_type(current_df, 'One Shot'):,.2f}")
    c5.metric("Past due Regular ($)", f"{sum_amt_type(past_due_df, 'Regular'):,.2f}")
    c6.metric("Past due One Shot ($)", f"{sum_amt_type(past_due_df, 'One Shot'):,.2f}")

    def cnt(x: pd.DataFrame) -> int:
        return int(len(x))

    def cnt_type(x: pd.DataFrame, t: str) -> int:
        if x.empty:
            return 0
        return int((x["invoice_type"] == t).sum())

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Current (count)", f"{cnt(current_df):,}")
    k2.metric("Past due (count)", f"{cnt(past_due_df):,}")
    k3.metric("Current Regular (count)", f"{cnt_type(current_df, 'Regular'):,}")
    k4.metric("Current One Shot (count)", f"{cnt_type(current_df, 'One Shot'):,}")
    k5.metric("Past due Regular (count)", f"{cnt_type(past_due_df, 'Regular'):,}")
    k6.metric("Past due One Shot (count)", f"{cnt_type(past_due_df, 'One Shot'):,}")
