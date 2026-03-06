"""
Klaviyo API client — pulls email/SMS campaign and flow performance
for inclusion in the daily ads digest.

Uses Klaviyo's private API key authentication.
API docs: https://developers.klaviyo.com/en/reference/api_overview
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

    def _get(self, endpoint: str, params: dict = None) -> dict:
        resp = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30)
        if not resp.ok:
            error = resp.json() if "json" in resp.headers.get("content-type", "") else resp.text
            raise Exception(f"Klaviyo API {resp.status_code}: {error}")
        return resp.json()

    def _post(self, endpoint: str, payload: dict) -> dict:
        resp = self.session.post(f"{BASE_URL}/{endpoint}", json=payload, timeout=30)
        if not resp.ok:
            error = resp.json() if "json" in resp.headers.get("content-type", "") else resp.text
            raise Exception(f"Klaviyo API {resp.status_code}: {error}")
        return resp.json()

    def get_daily_report(self, date: str) -> dict:
        """Pull a full daily Klaviyo performance report."""
        # Date range for the target day
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
        }

        # ── Query metric aggregates for the day ──────────────
        # Email metrics
        email_metrics = self._query_email_metrics(start, end)
        if email_metrics:
            report["summary"].update(email_metrics)

        # Revenue from Klaviyo-attributed orders
        revenue_data = self._query_revenue_metrics(start, end)
        if revenue_data:
            report["summary"]["revenue_attributed"] = revenue_data.get("revenue", 0)

        # ── Recent campaigns ─────────────────────────────────
        try:
            campaigns = self._get_recent_campaigns(date)
            report["campaigns"] = campaigns
        except Exception as e:
            logger.warning(f"Failed to fetch campaigns: {e}")

        # ── Flow performance ─────────────────────────────────
        try:
            flow_data = self._query_flow_metrics(start, end)
            if flow_data:
                report["flows_summary"] = flow_data
        except Exception as e:
            logger.warning(f"Failed to fetch flow metrics: {e}")

        # Calculate rates
        sent = report["summary"]["emails_sent"]
        delivered = report["summary"]["emails_delivered"]
        opened = report["summary"]["emails_opened"]
        clicked = report["summary"]["emails_clicked"]

        if delivered > 0:
            report["summary"]["open_rate"] = round((opened / delivered) * 100, 1)
            report["summary"]["click_rate"] = round((clicked / delivered) * 100, 1)

        return report

    def _query_email_metrics(self, start: str, end: str) -> dict:
        """Query aggregate email metrics for a time period."""
        metrics_to_query = [
            ("Received Email", "received"),
            ("Opened Email", "opened"),
            ("Clicked Email", "clicked"),
            ("Unsubscribed", "unsubscribed"),
        ]

        results = {}
        for metric_name, key in metrics_to_query:
            try:
                data = self._post("metric-aggregates", {
                    "data": {
                        "type": "metric-aggregate",
                        "attributes": {
                            "metric_id": self._get_metric_id(metric_name),
                            "measurements": ["count"],
                            "filter": [
                                "greater-or-equal(datetime," + start + ")",
                                "less-than(datetime," + end + ")",
                            ],
                            "interval": "day",
                        }
                    }
                })
                count = self._extract_aggregate_value(data)
                if key == "received":
                    results["emails_delivered"] = count
                    results["emails_sent"] = count  # Approximate
                elif key == "opened":
                    results["emails_opened"] = count
                elif key == "clicked":
                    results["emails_clicked"] = count
                elif key == "unsubscribed":
                    results["unsubscribes"] = count
            except Exception as e:
                logger.debug(f"Metric {metric_name} query failed: {e}")

        return results

    def _query_revenue_metrics(self, start: str, end: str) -> dict:
        """Query Klaviyo-attributed revenue."""
        try:
            metric_id = self._get_metric_id("Placed Order")
            data = self._post("metric-aggregates", {
                "data": {
                    "type": "metric-aggregate",
                    "attributes": {
                        "metric_id": metric_id,
                        "measurements": ["sum_value", "count"],
                        "filter": [
                            "greater-or-equal(datetime," + start + ")",
                            "less-than(datetime," + end + ")",
                        ],
                        "interval": "day",
                    }
                }
            })

            results = data.get("data", {}).get("attributes", {}).get("data", [])
            revenue = 0
            orders = 0
            for row in results:
                measurements = row.get("measurements", {})
                revenue += measurements.get("sum_value", 0)
                orders += measurements.get("count", 0)

            return {"revenue": round(revenue, 2), "orders": orders}
        except Exception as e:
            logger.debug(f"Revenue query failed: {e}")
            return {}

    def _query_flow_metrics(self, start: str, end: str) -> dict:
        """Query flow-attributed email sends and revenue."""
        # Get flow-attributed revenue via "Placed Order" filtered by $flow
        try:
            metric_id = self._get_metric_id("Received Email")
            data = self._post("metric-aggregates", {
                "data": {
                    "type": "metric-aggregate",
                    "attributes": {
                        "metric_id": metric_id,
                        "measurements": ["count"],
                        "group_by": ["$flow"],
                        "filter": [
                            "greater-or-equal(datetime," + start + ")",
                            "less-than(datetime," + end + ")",
                        ],
                        "interval": "day",
                    }
                }
            })

            results = data.get("data", {}).get("attributes", {}).get("data", [])
            total_flow_sends = 0
            for row in results:
                flow_id = row.get("dimensions", {}).get("$flow")
                if flow_id:  # Only count rows with a flow ID
                    measurements = row.get("measurements", {})
                    total_flow_sends += measurements.get("count", 0)

            return {
                "emails_sent": total_flow_sends,
                "revenue_attributed": 0,  # Would need separate query
            }
        except Exception as e:
            logger.debug(f"Flow metrics query failed: {e}")
            return {"emails_sent": 0, "revenue_attributed": 0}

    def _get_recent_campaigns(self, date: str) -> list:
        """Get campaigns sent on or near the target date."""
        try:
            data = self._get("campaigns", params={
                "filter": f"equals(messages.channel,'email')",
                "sort": "-send_time",
                "page[size]": 10,
            })

            campaigns = []
            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                send_time = attrs.get("send_time", "")

                # Only include campaigns from the target date
                if send_time and date in send_time:
                    campaigns.append({
                        "name": attrs.get("name", "Unknown"),
                        "status": attrs.get("status", ""),
                        "send_time": send_time,
                        "id": item.get("id", ""),
                    })

            return campaigns
        except Exception as e:
            logger.debug(f"Campaign fetch failed: {e}")
            return []

    def _get_metric_id(self, metric_name: str) -> str:
        """Look up a metric ID by name. Caches results."""
        if not hasattr(self, "_metric_cache"):
            self._metric_cache = {}

        if metric_name in self._metric_cache:
            return self._metric_cache[metric_name]

        # Fetch all metrics and cache
        try:
            data = self._get("metrics", params={"page[size]": 50})
            for item in data.get("data", []):
                name = item.get("attributes", {}).get("name", "")
                self._metric_cache[name] = item.get("id", "")
        except Exception as e:
            logger.error(f"Failed to fetch metrics list: {e}")

        if metric_name not in self._metric_cache:
            raise Exception(f"Metric '{metric_name}' not found in Klaviyo account")

        return self._metric_cache[metric_name]

    @staticmethod
    def _extract_aggregate_value(data: dict) -> float:
        """Extract a single aggregate value from metric-aggregates response."""
        results = data.get("data", {}).get("attributes", {}).get("data", [])
        total = 0
        for row in results:
            measurements = row.get("measurements", {})
            total += measurements.get("count", 0)
        return total
