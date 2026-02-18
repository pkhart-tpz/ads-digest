"""
Report Builder — generates a beautifully formatted HTML email
from the raw data and AI analysis. Now includes Shopify source-of-truth data.
"""

from meta_ads import MetaAdsClient


class ReportBuilder:
    def build(
        self,
        meta_data: dict,
        google_data: dict,
        shopify_data: dict,
        analysis: dict,
        date: str,
        brand: str,
    ) -> str:

        # ── Extract key metrics ──────────────────────────────────
        meta_summary = meta_data.get("account_summary", {})
        google_summary = google_data.get("account_summary", {})
        shop_summary = shopify_data.get("summary", {})

        meta_spend = float(meta_summary.get("spend", 0))
        google_spend = float(google_summary.get("spend", 0))
        total_spend = meta_spend + google_spend

        # Shopify = source of truth
        shopify_revenue = shop_summary.get("net_revenue", 0)
        shopify_orders = shop_summary.get("total_orders", 0)
        shopify_aov = shop_summary.get("average_order_value", 0)
        new_rate = shop_summary.get("new_customer_rate", 0)
        true_blended_roas = round(shopify_revenue / total_spend, 2) if total_spend > 0 else 0

        # Platform-claimed revenue (for attribution gap)
        meta_purchases = MetaAdsClient.extract_purchase_metrics(meta_summary)
        platform_claimed = meta_purchases["purchase_value"] + float(google_summary.get("conversion_value", 0))
        attribution_gap = round(((platform_claimed - shopify_revenue) / shopify_revenue) * 100, 1) if shopify_revenue > 0 else 0

        meta_clicks = int(meta_summary.get("clicks", 0))
        google_clicks = int(google_summary.get("clicks", 0))

        # Campaign tables
        meta_campaigns_html = self._build_meta_campaign_rows(meta_data.get("campaigns", []))
        google_campaigns_html = self._build_google_campaign_rows(google_data.get("campaigns", []))

        # Top products
        top_products_html = self._build_product_rows(shopify_data.get("top_products", []))

        # Discount codes
        discount_html = self._build_discount_rows(shopify_data.get("discount_codes", {}))

        # Inventory alerts
        inv_alerts = shopify_data.get("inventory_alerts", [])
        inventory_html = ""
        if inv_alerts:
            rows = ""
            for item in inv_alerts:
                color = "#ef4444" if item["quantity_remaining"] <= 3 else "#f59e0b"
                rows += f"""
                <tr>
                    <td style="padding:8px 10px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:13px;">{item['product']}</td>
                    <td style="padding:8px 10px;border-bottom:1px solid #1a1a2e;color:#9ca3af;font-size:13px;">{item.get('variant', '')}</td>
                    <td style="padding:8px 10px;border-bottom:1px solid #1a1a2e;color:{color};font-size:13px;font-weight:700;text-align:right;">{item['quantity_remaining']} left</td>
                </tr>"""
            inventory_html = f"""
            <div style="background:#1a0a0a;border:1px solid #7f1d1d;border-radius:8px;padding:16px 20px;margin:20px 0;">
                <div style="font-weight:700;color:#f87171;margin-bottom:10px;">🚨 Low Inventory Alert</div>
                <table style="width:100%;border-collapse:collapse;">{rows}</table>
            </div>"""

        # Anomalies
        anomalies = analysis.get("anomalies", [])
        anomalies_html = ""
        if anomalies:
            items = "".join(f'<li style="padding:4px 0;color:#fbbf24;">{a}</li>' for a in anomalies)
            anomalies_html = f"""
            <div style="background:#1a1a0a;border:1px solid #854d0e;border-radius:8px;padding:16px 20px;margin:20px 0;">
                <div style="font-weight:700;color:#fbbf24;margin-bottom:8px;">⚠️ Anomalies Detected</div>
                <ul style="margin:0;padding-left:20px;font-size:13px;">{items}</ul>
            </div>"""

        # Recommendations
        recs = analysis.get("recommendations", [])
        recs_html = ""
        for rec in recs:
            priority = rec.get("priority", "MEDIUM")
            color = {"HIGH": "#ef4444", "MEDIUM": "#f59e0b", "LOW": "#22c55e"}.get(priority, "#6b7280")
            recs_html += f"""
            <tr>
                <td style="padding:12px 16px;border-bottom:1px solid #1a1a2e;">
                    <span style="display:inline-block;padding:2px 10px;border-radius:4px;font-size:11px;font-weight:700;color:#fff;background:{color};letter-spacing:0.5px;">{priority}</span>
                </td>
                <td style="padding:12px 16px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:14px;">
                    <strong style="color:#fff;">{rec.get('action', '')}</strong><br>
                    <span style="color:#9ca3af;font-size:12px;">{rec.get('rationale', '')}</span>
                </td>
            </tr>"""

        # Attribution gap color
        gap_color = "#22c55e" if attribution_gap < 15 else "#f59e0b" if attribution_gap < 30 else "#ef4444"

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#0a0a1a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<div style="max-width:680px;margin:0 auto;padding:20px;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#0f0f2e 0%,#1a1a3e 100%);border-radius:12px;padding:32px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:12px;color:#6366f1;font-weight:700;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;">DAILY ADS DIGEST</div>
        <div style="font-size:28px;font-weight:800;color:#fff;margin-bottom:4px;">{brand}</div>
        <div style="font-size:14px;color:#9ca3af;">{date}</div>
    </div>

    <!-- Executive Summary -->
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#6366f1;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">Executive Summary</div>
        <div style="font-size:15px;color:#e0e0e0;line-height:1.7;">{analysis.get('executive_summary', 'No summary available.')}</div>
    </div>

    <!-- Source of Truth Banner -->
    <div style="background:linear-gradient(135deg,#052e16 0%,#0a3d1f 100%);border-radius:12px;padding:20px;margin-bottom:24px;border:1px solid #166534;">
        <div style="font-size:11px;color:#4ade80;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:12px;">📦 SHOPIFY — SOURCE OF TRUTH</div>
        <div style="display:flex;gap:16px;flex-wrap:wrap;">
            <div style="flex:1;min-width:100px;">
                <div style="font-size:10px;color:#6b9e7a;text-transform:uppercase;letter-spacing:0.8px;">Net Revenue</div>
                <div style="font-size:22px;font-weight:800;color:#4ade80;">${shopify_revenue:,.2f}</div>
            </div>
            <div style="flex:1;min-width:100px;">
                <div style="font-size:10px;color:#6b9e7a;text-transform:uppercase;letter-spacing:0.8px;">True ROAS</div>
                <div style="font-size:22px;font-weight:800;color:{'#4ade80' if true_blended_roas >= 3 else '#fbbf24' if true_blended_roas >= 2 else '#f87171'};">{true_blended_roas}x</div>
            </div>
            <div style="flex:1;min-width:100px;">
                <div style="font-size:10px;color:#6b9e7a;text-transform:uppercase;letter-spacing:0.8px;">Orders</div>
                <div style="font-size:22px;font-weight:800;color:#fff;">{shopify_orders}</div>
            </div>
            <div style="flex:1;min-width:100px;">
                <div style="font-size:10px;color:#6b9e7a;text-transform:uppercase;letter-spacing:0.8px;">AOV</div>
                <div style="font-size:22px;font-weight:800;color:#fff;">${shopify_aov:.2f}</div>
            </div>
            <div style="flex:1;min-width:100px;">
                <div style="font-size:10px;color:#6b9e7a;text-transform:uppercase;letter-spacing:0.8px;">New Customers</div>
                <div style="font-size:22px;font-weight:800;color:#fff;">{new_rate}%</div>
            </div>
        </div>
    </div>

    <!-- Attribution Gap Alert -->
    <div style="background:#111128;border-radius:12px;padding:18px 24px;margin-bottom:24px;border:1px solid #2a2a4e;display:flex;align-items:center;gap:20px;">
        <div>
            <div style="font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:1px;">Attribution Gap</div>
            <div style="font-size:20px;font-weight:800;color:{gap_color};">+{attribution_gap}%</div>
        </div>
        <div style="font-size:12px;color:#9ca3af;line-height:1.5;">
            Ad platforms claim <strong style="color:#fff;">${platform_claimed:,.2f}</strong> in revenue, but Shopify recorded <strong style="color:#fff;">${shopify_revenue:,.2f}</strong>. {'This gap is normal for multi-touch attribution.' if attribution_gap < 30 else 'This gap is high — platforms are significantly over-counting.'}
        </div>
    </div>

    <!-- KPI Cards -->
    <div style="display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap;">
        <div style="flex:1;min-width:140px;background:#111128;border-radius:12px;padding:20px;border:1px solid #2a2a4e;text-align:center;">
            <div style="font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Total Ad Spend</div>
            <div style="font-size:24px;font-weight:800;color:#fff;">${total_spend:,.2f}</div>
        </div>
        <div style="flex:1;min-width:140px;background:#111128;border-radius:12px;padding:20px;border:1px solid #2a2a4e;text-align:center;">
            <div style="font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Total Clicks</div>
            <div style="font-size:24px;font-weight:800;color:#fff;">{meta_clicks + google_clicks:,}</div>
        </div>
        <div style="flex:1;min-width:140px;background:#111128;border-radius:12px;padding:20px;border:1px solid #2a2a4e;text-align:center;">
            <div style="font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Cost Per Order</div>
            <div style="font-size:24px;font-weight:800;color:#fff;">${total_spend / shopify_orders:,.2f}</div>
        </div>
        <div style="flex:1;min-width:140px;background:#111128;border-radius:12px;padding:20px;border:1px solid #2a2a4e;text-align:center;">
            <div style="font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Discount Impact</div>
            <div style="font-size:24px;font-weight:800;color:#f59e0b;">${shop_summary.get('total_discount_amount', 0):,.2f}</div>
        </div>
    </div>

    {inventory_html}
    {anomalies_html}

    <!-- Platform Comparison -->
    <div style="display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap;">
        <div style="flex:1;min-width:280px;background:#111128;border-radius:12px;padding:20px;border:1px solid #2a2a4e;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
                <div style="width:8px;height:8px;border-radius:50%;background:#3b82f6;"></div>
                <div style="font-size:14px;font-weight:700;color:#fff;">Meta Ads</div>
            </div>
            <div style="font-size:12px;color:#9ca3af;margin-bottom:4px;">Spend: <span style="color:#fff;font-weight:600;">${meta_spend:,.2f}</span></div>
            <div style="font-size:12px;color:#9ca3af;margin-bottom:4px;">Claimed ROAS: <span style="color:#fff;font-weight:600;">{meta_purchases['roas']}x</span></div>
            <div style="font-size:12px;color:#9ca3af;">Clicks: <span style="color:#fff;font-weight:600;">{meta_clicks:,}</span></div>
        </div>
        <div style="flex:1;min-width:280px;background:#111128;border-radius:12px;padding:20px;border:1px solid #2a2a4e;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
                <div style="width:8px;height:8px;border-radius:50%;background:#22c55e;"></div>
                <div style="font-size:14px;font-weight:700;color:#fff;">Google Ads</div>
            </div>
            <div style="font-size:12px;color:#9ca3af;margin-bottom:4px;">Spend: <span style="color:#fff;font-weight:600;">${google_spend:,.2f}</span></div>
            <div style="font-size:12px;color:#9ca3af;margin-bottom:4px;">Claimed ROAS: <span style="color:#fff;font-weight:600;">{float(google_summary.get('roas', 0))}x</span></div>
            <div style="font-size:12px;color:#9ca3af;">Clicks: <span style="color:#fff;font-weight:600;">{google_clicks:,}</span></div>
        </div>
    </div>

    <!-- Meta Campaign Breakdown -->
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#3b82f6;letter-spacing:1px;text-transform:uppercase;margin-bottom:16px;">Meta Campaigns</div>
        <table style="width:100%;border-collapse:collapse;">
            <tr style="border-bottom:2px solid #2a2a4e;">
                <th style="text-align:left;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Campaign</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Spend</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">ROAS</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Clicks</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">CTR</th>
            </tr>
            {meta_campaigns_html}
        </table>
    </div>

    <!-- Google Campaign Breakdown -->
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#22c55e;letter-spacing:1px;text-transform:uppercase;margin-bottom:16px;">Google Campaigns</div>
        <table style="width:100%;border-collapse:collapse;">
            <tr style="border-bottom:2px solid #2a2a4e;">
                <th style="text-align:left;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Campaign</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Spend</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">ROAS</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Conv.</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">CPC</th>
            </tr>
            {google_campaigns_html}
        </table>
    </div>

    <!-- Top Products -->
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#a855f7;letter-spacing:1px;text-transform:uppercase;margin-bottom:16px;">🏆 Top Products (Shopify)</div>
        <table style="width:100%;border-collapse:collapse;">
            <tr style="border-bottom:2px solid #2a2a4e;">
                <th style="text-align:left;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Product</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Units</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Revenue</th>
            </tr>
            {top_products_html}
        </table>
    </div>

    <!-- Discount Codes -->
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#f59e0b;letter-spacing:1px;text-transform:uppercase;margin-bottom:16px;">🏷️ Discount Codes Used</div>
        <table style="width:100%;border-collapse:collapse;">
            <tr style="border-bottom:2px solid #2a2a4e;">
                <th style="text-align:left;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Code</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Uses</th>
                <th style="text-align:right;padding:8px;color:#9ca3af;font-size:11px;text-transform:uppercase;">Total Discount</th>
            </tr>
            {discount_html}
        </table>
    </div>

    <!-- Deep Analysis -->
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#6366f1;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">📱 Meta Analysis</div>
        <div style="font-size:14px;color:#d1d5db;line-height:1.7;">{analysis.get('meta_analysis', 'N/A')}</div>
    </div>
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#6366f1;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">🔍 Google Analysis</div>
        <div style="font-size:14px;color:#d1d5db;line-height:1.7;">{analysis.get('google_analysis', 'N/A')}</div>
    </div>
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#6366f1;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">📦 Shopify Analysis</div>
        <div style="font-size:14px;color:#d1d5db;line-height:1.7;">{analysis.get('shopify_analysis', 'N/A')}</div>
    </div>
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#6366f1;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">🔀 Attribution Gap</div>
        <div style="font-size:14px;color:#d1d5db;line-height:1.7;">{analysis.get('attribution_gap', 'N/A')}</div>
    </div>
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#6366f1;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">🎨 Creative Insights</div>
        <div style="font-size:14px;color:#d1d5db;line-height:1.7;">{analysis.get('creative_insights', 'N/A')}</div>
    </div>
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#6366f1;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">👥 Audience Insights</div>
        <div style="font-size:14px;color:#d1d5db;line-height:1.7;">{analysis.get('audience_insights', 'N/A')}</div>
    </div>

    <!-- Recommendations -->
    <div style="background:#111128;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #2a2a4e;">
        <div style="font-size:13px;font-weight:700;color:#f59e0b;letter-spacing:1px;text-transform:uppercase;margin-bottom:16px;">🎯 Recommendations</div>
        <table style="width:100%;border-collapse:collapse;">{recs_html}</table>
    </div>

    <!-- Budget Suggestion -->
    <div style="background:linear-gradient(135deg,#0f2027 0%,#0a1628 100%);border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #1e3a5f;">
        <div style="font-size:13px;font-weight:700;color:#38bdf8;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">💰 Budget Recommendation</div>
        <div style="font-size:14px;color:#d1d5db;line-height:1.7;">{analysis.get('budget_suggestion', 'N/A')}</div>
    </div>

    <!-- Footer -->
    <div style="text-align:center;padding:20px;color:#4b5563;font-size:11px;">
        TPZ Holdings · Daily Ads Digest · Powered by Claude AI<br>
        This report was auto-generated. Reply to this email with questions.
    </div>
</div>
</body>
</html>"""

        return html

    def _build_meta_campaign_rows(self, campaigns: list) -> str:
        rows = ""
        for c in campaigns:
            spend = float(c.get("spend", 0))
            pm = MetaAdsClient.extract_purchase_metrics(c)
            roas = pm["roas"]
            clicks = int(c.get("clicks", 0))
            ctr = float(c.get("ctr", 0))
            name = c.get("campaign_name", "Unknown")
            roas_color = "#22c55e" if roas >= 3 else "#f59e0b" if roas >= 2 else "#ef4444"
            rows += f"""<tr>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:13px;">{name[:40]}</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#fff;font-size:13px;text-align:right;">${spend:,.2f}</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:{roas_color};font-size:13px;text-align:right;font-weight:700;">{roas}x</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:13px;text-align:right;">{clicks:,}</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:13px;text-align:right;">{ctr:.2f}%</td>
            </tr>"""
        return rows or '<tr><td colspan="5" style="padding:12px;color:#6b7280;text-align:center;">No data</td></tr>'

    def _build_google_campaign_rows(self, campaigns: list) -> str:
        rows = ""
        for c in campaigns:
            roas = c.get("roas", 0)
            roas_color = "#22c55e" if roas >= 3 else "#f59e0b" if roas >= 2 else "#ef4444"
            rows += f"""<tr>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:13px;">{c.get('name', '')[:40]}</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#fff;font-size:13px;text-align:right;">${c.get('spend', 0):,.2f}</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:{roas_color};font-size:13px;text-align:right;font-weight:700;">{roas}x</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:13px;text-align:right;">{c.get('conversions', 0):.1f}</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:13px;text-align:right;">${c.get('avg_cpc', 0):.2f}</td>
            </tr>"""
        return rows or '<tr><td colspan="5" style="padding:12px;color:#6b7280;text-align:center;">No data</td></tr>'

    def _build_product_rows(self, products: list) -> str:
        rows = ""
        for p in products:
            rows += f"""<tr>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:13px;">{p['name'][:45]}</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:13px;text-align:right;">{p['units']}</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#22c55e;font-size:13px;text-align:right;font-weight:600;">${p['revenue']:,.2f}</td>
            </tr>"""
        return rows or '<tr><td colspan="3" style="padding:12px;color:#6b7280;text-align:center;">No data</td></tr>'

    def _build_discount_rows(self, codes: dict) -> str:
        rows = ""
        for code, data in sorted(codes.items(), key=lambda x: x[1]["uses"], reverse=True):
            rows += f"""<tr>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#fbbf24;font-size:13px;font-weight:600;">{code}</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#e0e0e0;font-size:13px;text-align:right;">{data['uses']}</td>
                <td style="padding:10px 8px;border-bottom:1px solid #1a1a2e;color:#f59e0b;font-size:13px;text-align:right;">${data['total_discount']:,.2f}</td>
            </tr>"""
        return rows or '<tr><td colspan="3" style="padding:12px;color:#6b7280;text-align:center;">No codes used</td></tr>'
