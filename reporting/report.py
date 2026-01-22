from pathlib import Path
from jinja2 import Environment, FileSystemLoader


class ClientReportGenerator:
    def __init__(self, template_dir, output_dir="output"):
        self.template_dir = Path(template_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=True,
        )

    def generate_html(
        self,
        df,
        client_col,      # ← sigue viniendo del dashboard (buyer)
        amount_col,
        output_name,
        hide_columns=None,
    ):
        hide_columns = set(hide_columns or [])

        # ⚠️ vendor column is inferred here (no dashboard change)
        vendor_col = "vendor_company_name"
        buyer_col = client_col

        vendors = []

        for vendor, df_vendor in df.groupby(vendor_col):
            buyers = []
            vendor_total = float(df_vendor[amount_col].sum())

            for buyer, df_buyer in df_vendor.groupby(buyer_col):
                # drop columns ONLY for rendering
                g_render = df_buyer.drop(
                    columns=[
                        c for c in (*hide_columns, vendor_col, buyer_col)
                        if c in df_buyer.columns
                    ],
                    errors="ignore",
                )

                buyers.append({
                    "buyer": buyer,
                    "rows": g_render.to_dict(orient="records"),
                    "subtotal": float(df_buyer[amount_col].sum()),
                })

            vendors.append({
                "vendor": vendor,
                "buyers": buyers,
                "vendor_total": vendor_total,
            })

        context = {
            "vendors": vendors,
            "grand_total": float(df[amount_col].sum()),
        }

        html = self.env.get_template("report.html").render(**context)

        output_path = self.output_dir / output_name
        output_path.write_text(html, encoding="utf-8")

        return output_path
