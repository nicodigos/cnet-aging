import streamlit as st
import pandas as pd


TAX_COLUMNS = [
    "gst_qc",
    "qst_qc",
    "hst_on",
    "gst_ab",
    "gst_bc",
    "pst_bc",
    "hst_nb",
    "pst_mb",
    "gst_mb",
    "hst_nl",
    "gst_nt",
    "hst_ns",
    "gst_nu",
    "hst_pe",
    "pst_sk",
    "gst_sk",
    "gst_yt",
]


def render_past_due_table(table_df: pd.DataFrame):
    st.divider()
    st.subheader("Unpaid Table")

    table_df = table_df.copy()
    if "partial_payments_amount" in table_df.columns:
        table_df["partially_paid"] = table_df["partial_payments_amount"].fillna(0)
    if "open_amount_with_taxes" in table_df.columns:
        table_df["total_amount_with_taxes"] = (
            table_df["open_amount_with_taxes"].fillna(table_df["total_amount_with_taxes"])
        )

    cols = [
        "invoice_id",
        "po_number",
        "building_address",
        "issue_date",
        "invoice_type",
        "past_due",
        "buyer_company_name",
        "vendor_company_name",
        "payment_status",
        "days_since_issue",
        "total_amount_without_taxes",
        "total_amount_with_taxes",
        *TAX_COLUMNS,
        "partially_paid",
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
    money_cols = [
        c
        for c in [
            "total_amount_without_taxes",
            "total_amount_with_taxes",
            *TAX_COLUMNS,
            "partially_paid",
        ]
        if c in table_df.columns
    ]
    if money_cols:
        style = style.format({c: "{:,.2f}" for c in money_cols})

    def apply_cell_style(styler, func, subset):
        # pandas newer versions use Styler.map; older ones still expose applymap.
        if hasattr(styler, "map"):
            return styler.map(func, subset=subset)
        return styler.applymap(func, subset=subset)

    if "past_due" in table_df.columns:
        style = apply_cell_style(style, color_past_due, subset=["past_due"])

    if "days_since_issue" in table_df.columns:
        col = "days_since_issue"
        s = pd.to_numeric(table_df[col], errors="coerce")

        if s.notna().any():
            max_abs = max(abs(s.min()), abs(s.max()))

            style = style.background_gradient(
                subset=[col],
                cmap="RdBu_r",   # Blue (neg) → White (0) → Red (pos)
                vmin=-max_abs,
                vmax=max_abs,
            )


    if "total_amount_with_taxes" in table_df.columns:
        style = style.background_gradient(subset=["total_amount_with_taxes"], cmap="Greens")

    st.dataframe(style, use_container_width=True, height=650, hide_index=True)
