import pandas as pd
import streamlit as st


def render_metrics(df_f: pd.DataFrame):
    current_df = df_f[~df_f["past_due"]]
    past_due_df = df_f[df_f["past_due"]]

    def sum_amt(x: pd.DataFrame) -> float:
        return float(x["total_amount_with_taxes"].sum()) if not x.empty else 0.0

    def cnt(x: pd.DataFrame) -> int:
        return int(len(x)) if not x.empty else 0

    total_df = df_f  # already unpaid by assumption

    # ---------- AMOUNTS ----------
    c1, c2, c3 = st.columns(3)
    c1.metric("Current ($)", f"{sum_amt(current_df):,.2f}")
    c2.metric("Past Due ($)", f"{sum_amt(past_due_df):,.2f}")
    c3.metric("Total Unpaid ($)", f"{sum_amt(total_df):,.2f}")

    # ---------- COUNTS ----------
    k1, k2, k3 = st.columns(3)
    k1.metric("Current (count)", f"{cnt(current_df):,}")
    k2.metric("Past Due (count)", f"{cnt(past_due_df):,}")
    k3.metric("Total Unpaid (count)", f"{cnt(total_df):,}")
