"""
Klaviyo API client — pulls email/SMS marketing performance
for inclusion in the daily ads digest.

Uses Klaviyo private API key authentication.
"""

import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("ads-digest.klaviyo")

BASE_URL = "https://a.klaviyo.com/api"
API_REVISION = "2024-10-15"


class KlaviyoClient:
    def __init__(self, private_api_key: str):
        self.api_key = private_api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Klaviyo-API-Key {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "revision": API_REVISION,
        })
        self._metric_cache = {}

    def _get(self, endpoint: str, params: dict = None) -> dict:
        resp = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30)
        if not resp.ok:
            error = resp.text[:500]
            raise Exception(f"Klaviyo GET {endpoint} {resp.status_code}: {error}")
        return resp.json()

    def _post(self, endpoint: str, payload: dict) -> dict:
        resp = self.session.post(f"{BASE_URL}/{endpoint}", json=payload, timeout=30)
        if not resp.ok:
            error = resp.text[:500]
            raise Exception(f"Klaviyo POST {endpoint} {resp.status_code}: {error}")
        return resp.json()

    def get_daily_report(self, date: str) -> dict:
        """Pull a full daily Klaviyo performance report."""
        start = f"{date}T00:00:00+00:00"
        end_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        end = f"{end_date}T00:00:00+00:00"

        report = {
            "platform": "klaviyo",
            "date": date,
            "summary": {
                "emails_sent": 0,
                "emails_delivered": 0,
                "emails_opened": 0,
                "emails_clicked": 0,
                "open_rate": 0,
                "click_rate": 0,
                "unsubscribes": 0,
                "revenue_attributed": 0,
                "sms_sent": 0,
                "sms_clicked": 0,
            },
            "campaigns": [],
            "flows_summary": {
                "emails_sent": 0,
                "revenue_attributed": 0,
            },
            "available_metrics": [],
            "errors": [],
        }

        # Step 1: Load all available metrics so we know what's in this account
        try:
            self._load_metrics()
            report["available_metrics"] = list(self._metric_cache.keys())
            logger.info(f"Klaviyo: Found {len(self._metric_cache)} metrics: {', '.join(list(self._metric_cache.keys())[:15])}")
        except Exception as e:
            report["errors"].append(f"Failed to load metrics: {e}")
            logger.error(f"Klaviyo metrics load failed: {e}")
            return report

        # Step 2: Query each metric we care about
        # Map of what we want -> possible metric names in Klaviyo
        metric_map = {
            "emails_delivered": ["Received Email"],
            "emails_opened": ["Opened Email"],
            "emails_clicked": ["Clicked Email"],
            "unsubscribes": ["Unsubscribed", "Unsubscribed from List"],
            "sms_sent": ["Received SMS"],
            "sms_clicked": ["Clicked SMS"],
        }

        for key, possible_names in metric_map.items():
            metric_id = None
            metric_name = None
            for name in possible_names:
                if name in self._metric_cache:
                    metric_id = self._metric_cache[name]
                    metric_name = name
                    break

            if not metric_id:
                logger.debug(f"Klaviyo: No metric found for {key} (tried: {possible_names})")
                continue

            try:
                count = self._query_metric_count(metric_id, start, end)
                report["summary"][key] = count
                if key == "emails_delivered":
                    report["summary"]["emails_sent"] = count
                logger.info(f"Klaviyo {metric_name}: {count}")
            except Exception as e:
                report["errors"].append(f"{metric_name}: {e}")
                logger.warning(f"Klaviyo metric {metric_name} failed: {e}")

        # Step 3: Revenue from Placed Order
        if "Placed Order" in self._metric_cache:
            try:
                rev_data = self._query_metric_revenue(
                    self._metric_cache["Placed Order"], start, end
                )
                report["summary"]["revenue_attributed"] = rev_data.get("revenue", 0)
                logger.info(f"Klaviyo revenue: ${rev_data.get('revenue', 0):.2f}")
            except Exception as e:
                report["errors"].append(f"Placed Order revenue: {e}")
                logger.warning(f"Klaviyo revenue query failed: {e}")
        else:
            logger.info("Klaviyo: No 'Placed Order' metric found")

        # Step 4: Calculate rates
        delivered = report["summary"]["emails_delivered"]
        opened = report["summary"]["emails_opened"]
        clicked = report["summary"]["emails_clicked"]

        if delivered > 0:
            report["summary"]["open_rate"] = round((opened / delivered) * 100, 1)
            report["summary"]["click_rate"] = round((clicked / delivered) * 100, 1)

        return report

    def _load_metrics(self):
        """Fetch all metrics and cache name -> ID mapping."""
        if self._metric_cache:
            return

        cursor = None
        while True:
            params = {"page[size]": 50}
            if cursor:
                params["page[cursor]"] = cursor

            data = self._get("metrics", params=params)

            for item in data.get("data", []):
                name = item.get("attributes", {}).get("name", "")
                mid = item.get("id", "")
                if name and mid:
                    self._metric_cache[name] = mid

            # Check for next page
            next_link = data.get("links", {}).get("next")
            if not next_link:
                break
            # Extract cursor from next link
            import urllib.parse
            parsed = urllib.parse.urlparse(next_link)
            qs = urllib.parse.parse_qs(parsed.query)
            cursor = qs.get("page[cursor]", [None])[0]
            if not cursor:
                break

    def _query_metric_count(self, metric_id: str, start: str, end: str) -> int:
        """Query count of a metric in a time range."""
        data = self._post("metric-aggregates", {
            "data": {
                "type": "metric-aggregate",
                "attributes": {
                    "metric_id": metric_id,
                    "measurements": ["count"],
                    "filter": [
                        f"greater-or-equal(datetime,{start})",
                        f"less-than(datetime,{end})",
                    ],
                    "interval": "day",
                }
            }
        })

        total = 0
        for row in data.get("data", {}).get("attributes", {}).get("data", []):
            measurements = row.get("measurements", {})
            total += measurements.get("count", 0)
        return int(total)

    def _query_metric_revenue(self, metric_id: str, start: str, end: str) -> dict:
        """Query revenue (sum_value) for a metric like Placed Order."""
        data = self._post("metric-aggregates", {
            "data": {
                "type": "metric-aggregate",
                "attributes": {
                    "metric_id": metric_id,
                    "measurements": ["sum_value", "count"],
                    "filter": [
                        f"greater-or-equal(datetime,{start})",
                        f"less-than(datetime,{end})",
                    ],
                    "interval": "day",
                }
            }
        })

        revenue = 0
        orders = 0
        for row in data.get("data", {}).get("attributes", {}).get("data", []):
            measurements = row.get("measurements", {})
            revenue += measurements.get("sum_value", 0)
            orders += measurements.get("count", 0)

        return {"revenue": round(revenue, 2), "orders": int(orders)}
