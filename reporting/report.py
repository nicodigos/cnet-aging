# reporting/report.py
from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable, Optional

from jinja2 import Environment, FileSystemLoader


def sanitize_path_part(s: str, maxlen: int = 80) -> str:
    """
    Make a safe folder/file name fragment.
    """
    s = (s or "").strip()
    s = re.sub(r"[^\w\-. ]+", "_", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s)
    s = s.strip("._-")
    return (s[:maxlen] or "(null)")


class ClientReportGenerator:
    """
    Generates HTML reports using Jinja2 templates.

    - generate_html(): one big report.html output (vendors -> buyers -> rows)
    - generate_html_partitioned(): many reports organized as Vendor/Buyer/report.html
      rendered with report_partition.html
    """

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
        client_col,  # buyer column from dashboard
        amount_col,
        output_name,
        hide_columns: Optional[Iterable[str]] = None,
        *,
        template_name: str = "report.html",
    ) -> Path:
        """
        Full report (single HTML file) with structure:
          vendors: [{vendor, vendor_total, buyers:[{buyer, rows, subtotal}]}]
          grand_total
        """
        hide_columns = set(hide_columns or [])

        vendor_col = "vendor_company_name"
        buyer_col = client_col

        vendors = []
        for vendor, df_vendor in df.groupby(vendor_col):
            buyers = []
            vendor_total = float(df_vendor[amount_col].sum())

            for buyer, df_buyer in df_vendor.groupby(buyer_col):
                g_render = df_buyer.drop(
                    columns=[
                        c for c in (*hide_columns, vendor_col, buyer_col)
                        if c in df_buyer.columns
                    ],
                    errors="ignore",
                )

                buyers.append(
                    {
                        "buyer": buyer,
                        "rows": g_render.to_dict(orient="records"),
                        "subtotal": float(df_buyer[amount_col].sum()),
                    }
                )

            vendors.append(
                {
                    "vendor": vendor,
                    "buyers": buyers,
                    "vendor_total": vendor_total,
                }
            )

        context = {
            "vendors": vendors,
            "grand_total": float(df[amount_col].sum()),
        }

        html = self.env.get_template(template_name).render(**context)

        output_path = self.output_dir / output_name
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def generate_html_partitioned(
        self,
        df,
        client_col,  # buyer column from dashboard
        amount_col,
        *,
        output_root_name: str = "reports_by_vendor_buyer",
        report_filename: str = "report.html",
        hide_columns: Optional[Iterable[str]] = None,
        include_index_html: bool = True,
        template_name: str = "report_partition.html",
    ) -> Path:
        """
        Creates a folder tree like:

        output/<output_root_name>/
          VendorA/
            BuyerX/
              report.html
            BuyerY/
              report.html
          VendorB/
            BuyerZ/
              report.html
          index.html   (optional)

        Returns: root directory path for the generated tree.

        NOTE: This writes to disk. For Streamlit Cloud, you can still write to /tmp
        and then ZIP it for download.
        """
        hide_columns = set(hide_columns or [])

        vendor_col = "vendor_company_name"
        buyer_col = client_col

        root_dir = self.output_dir / output_root_name
        root_dir.mkdir(parents=True, exist_ok=True)

        grand_total = float(df[amount_col].sum())
        index_entries = []

        for vendor, df_vendor in df.groupby(vendor_col):
            vendor_total = float(df_vendor[amount_col].sum())
            vendor_dir = root_dir / sanitize_path_part(str(vendor), maxlen=80)
            vendor_dir.mkdir(parents=True, exist_ok=True)

            for buyer, df_buyer in df_vendor.groupby(buyer_col):
                buyer_total = float(df_buyer[amount_col].sum())
                buyer_dir = vendor_dir / sanitize_path_part(str(buyer), maxlen=80)
                buyer_dir.mkdir(parents=True, exist_ok=True)

                g_render = df_buyer.drop(
                    columns=[
                        c for c in (*hide_columns, vendor_col, buyer_col)
                        if c in df_buyer.columns
                    ],
                    errors="ignore",
                )

                context = {
                    "vendor": vendor,
                    "buyer": buyer,
                    "rows": g_render.to_dict(orient="records"),
                    "buyer_total": buyer_total,
                    # keep in context in case you want them later, but template no longer shows them
                    "vendor_total": vendor_total,
                    "grand_total": grand_total,
                }

                html = self.env.get_template(template_name).render(**context)

                out_path = buyer_dir / report_filename
                out_path.write_text(html, encoding="utf-8")

                if include_index_html:
                    rel = out_path.relative_to(root_dir).as_posix()
                    index_entries.append(
                        {
                            "vendor": vendor,
                            "buyer": buyer,
                            "buyer_total": buyer_total,
                            "href": rel,
                        }
                    )

        if include_index_html:
            lines = [
                "<!doctype html>",
                "<html><head><meta charset='utf-8'>",
                "<title>Reports</title>",
                "<style>body{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px}"
                "table{border-collapse:collapse;width:100%}"
                "th,td{border:1px solid #ddd;padding:8px}"
                "th{text-align:left;background:#f6f6f6}"
                "</style></head><body>",
                "<h1>Reports by Vendor / Buyer</h1>",
                "<table>",
                "<thead><tr><th>Vendor</th><th>Buyer</th><th>Buyer total</th><th>Link</th></tr></thead>",
                "<tbody>",
            ]
            for e in index_entries:
                lines.append(
                    "<tr>"
                    f"<td>{e['vendor']}</td>"
                    f"<td>{e['buyer']}</td>"
                    f"<td>{e['buyer_total']:.2f}</td>"
                    f"<td><a href='{e['href']}'>report</a></td>"
                    "</tr>"
                )
            lines += ["</tbody></table>", "</body></html>"]

            (root_dir / "index.html").write_text("\n".join(lines), encoding="utf-8")

        return root_dir
