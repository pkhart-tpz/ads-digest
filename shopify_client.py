"""
Shopify Admin API client (Dev Dashboard / Client Credentials Grant).

As of January 2026, Shopify no longer lets you create "legacy" custom apps
with permanent access tokens. New apps must be created via the Dev Dashboard,
and access tokens are obtained programmatically using the client credentials
grant. Tokens expire every 24 hours — this client handles that automatically.
"""

import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("ads-digest.shopify")

API_VERSION = "2025-01"


class ShopifyClient:
    def __init__(self, shop_domain: str, client_id: str, client_secret: str):
        """
        shop_domain: your-store.myshopify.com
        client_id: from Dev Dashboard → Settings
        client_secret: from Dev Dashboard → Settings
        """
        self.shop_domain = shop_domain
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = f"https://{shop_domain}/admin/api/{API_VERSION}"
        self._access_token = None
        self.session = requests.Session()

    def _get_access_token(self) -> str:
        """
        Exchange client credentials for an access token.
        Tokens last 24 hours — we request a fresh one each run.
        """
        if self._access_token:
            return self._access_token

        token_url = f"https://{self.shop_domain}/admin/oauth/access_token"

        resp = requests.post(token_url, json={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        })
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]

        # Set up session headers for all subsequent requests
        self.session.headers.update({
            "X-Shopify-Access-Token": self._access_token,
            "Content-Type": "application/json",
        })

        logger.info("Shopify access token acquired successfully")
        return self._access_token

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Make an authenticated GET request to the Shopify Admin API."""
        self._get_access_token()  # Ensure we have a valid token
        url = f"{self.base_url}/{endpoint}.json"
        resp = self.session.get(url, params=params or {})
        resp.raise_for_status()
        return resp.json()

    def _get_all_pages(self, endpoint: str, params: dict, resource_key: str) -> list:
        """Handle Shopify's cursor-based pagination."""
        self._get_access_token()  # Ensure we have a valid token
        all_results = []
        url = f"{self.base_url}/{endpoint}.json"

        while url:
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            all_results.extend(data.get(resource_key, []))

            # Check for next page via Link header
            link_header = resp.headers.get("Link", "")
            url = None
            params = None  # Params are embedded in the next URL
            if 'rel="next"' in link_header:
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")
                        break

        return all_results

    def get_daily_report(self, date: str) -> dict:
        """
        Pull a complete daily sales report.

        Returns:
        {
            "platform": "shopify",
            "date": "2026-02-12",
            "summary": {
                "total_orders": int,
                "total_revenue": float,
                "total_refunds": float,
                "net_revenue": float,
                "average_order_value": float,
                "total_units_sold": int,
                "total_discount_amount": float,
                "new_customers": int,
                "returning_customers": int,
            },
            "orders": [...],
            "top_products": [...],
            "discount_codes": {...},
            "hourly_orders": [...],
        }
        """
        # Build date range (full day in UTC)
        start = f"{date}T00:00:00-00:00"
        end_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        end = f"{end_date}T00:00:00-00:00"

        # ── Pull orders ──────────────────────────────────────────
        logger.info(f"Pulling Shopify orders for {date}")
        orders = self._get_all_pages("orders", {
            "created_at_min": start,
            "created_at_max": end,
            "status": "any",
            "limit": 250,
            "fields": "id,name,created_at,total_price,subtotal_price,total_discounts,"
                      "total_tax,financial_status,fulfillment_status,discount_codes,"
                      "line_items,customer,referring_site,landing_site,"
                      "source_name,cancelled_at,refunds",
        }, "orders")
        logger.info(f"Found {len(orders)} orders")

        # ── Process orders ───────────────────────────────────────
        total_revenue = 0.0
        total_refunds = 0.0
        total_discounts = 0.0
        total_units = 0
        new_customers = 0
        returning_customers = 0
        product_sales = {}
        discount_code_usage = {}
        hourly_buckets = {str(h).zfill(2): 0 for h in range(24)}
        valid_orders = []

        for order in orders:
            if order.get("cancelled_at"):
                continue

            price = float(order.get("total_price", 0))
            discounts = float(order.get("total_discounts", 0))
            total_revenue += price
            total_discounts += discounts

            for refund in order.get("refunds", []):
                for txn in refund.get("transactions", []):
                    total_refunds += float(txn.get("amount", 0))

            for item in order.get("line_items", []):
                qty = item.get("quantity", 0)
                total_units += qty
                product_name = item.get("title", "Unknown")
                product_revenue = float(item.get("price", 0)) * qty
                if product_name not in product_sales:
                    product_sales[product_name] = {"units": 0, "revenue": 0.0}
                product_sales[product_name]["units"] += qty
                product_sales[product_name]["revenue"] += product_revenue

            customer = order.get("customer", {})
            if customer:
                if customer.get("orders_count", 1) <= 1:
                    new_customers += 1
                else:
                    returning_customers += 1

            for dc in order.get("discount_codes", []):
                code = dc.get("code", "none")
                amount = float(dc.get("amount", 0))
                if code not in discount_code_usage:
                    discount_code_usage[code] = {"uses": 0, "total_discount": 0.0}
                discount_code_usage[code]["uses"] += 1
                discount_code_usage[code]["total_discount"] += amount

            created = order.get("created_at", "")
            if created:
                try:
                    hour = datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%H")
                    hourly_buckets[hour] = hourly_buckets.get(hour, 0) + 1
                except (ValueError, AttributeError):
                    pass

            valid_orders.append({
                "name": order.get("name"),
                "total": price,
                "items": len(order.get("line_items", [])),
                "source": order.get("source_name", "unknown"),
                "new_customer": customer.get("orders_count", 1) <= 1 if customer else True,
            })

        top_products = sorted(
            [{"name": k, **v} for k, v in product_sales.items()],
            key=lambda x: x["revenue"],
            reverse=True,
        )[:10]

        order_count = len(valid_orders)
        net_revenue = total_revenue - total_refunds
        aov = net_revenue / order_count if order_count > 0 else 0

        return {
            "platform": "shopify",
            "date": date,
            "summary": {
                "total_orders": order_count,
                "total_revenue": round(total_revenue, 2),
                "total_refunds": round(total_refunds, 2),
                "net_revenue": round(net_revenue, 2),
                "average_order_value": round(aov, 2),
                "total_units_sold": total_units,
                "total_discount_amount": round(total_discounts, 2),
                "new_customers": new_customers,
                "returning_customers": returning_customers,
                "new_customer_rate": round(new_customers / order_count * 100, 1) if order_count > 0 else 0,
            },
            "orders": valid_orders,
            "top_products": top_products,
            "discount_codes": discount_code_usage,
            "hourly_orders": [{"hour": h, "count": c} for h, c in sorted(hourly_buckets.items())],
        }

    def get_inventory_alerts(self, threshold: int = 10) -> list:
        """Pull products with low inventory."""
        logger.info(f"Checking inventory levels (threshold: {threshold} units)")
        products = self._get_all_pages("products", {
            "status": "active",
            "limit": 250,
            "fields": "id,title,variants",
        }, "products")

        low_stock = []
        for product in products:
            for variant in product.get("variants", []):
                qty = variant.get("inventory_quantity", 0)
                if qty is not None and qty <= threshold:
                    low_stock.append({
                        "product": product.get("title"),
                        "variant": variant.get("title"),
                        "sku": variant.get("sku"),
                        "quantity_remaining": qty,
                    })

        return sorted(low_stock, key=lambda x: x["quantity_remaining"])
