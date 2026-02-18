"""
Meta Marketing API client.
Pulls campaign, ad set, and ad-level performance for a given day.
"""

import requests
import logging

logger = logging.getLogger("ads-digest.meta")

API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"


class MetaAdsClient:
    def __init__(self, access_token: str, ad_account_id: str):
        self.access_token = access_token
        self.ad_account_id = ad_account_id
        self.session = requests.Session()
        self.session.params = {"access_token": self.access_token}

    def _insights_request(self, level: str, date: str, fields: list[str]) -> list[dict]:
        """Generic insights pull at a given level."""
        url = f"{BASE_URL}/{self.ad_account_id}/insights"
        params = {
            "level": level,
            "time_range": f'{{"since":"{date}","until":"{date}"}}',
            "fields": ",".join(fields),
            "limit": 500,
        }
        results = []
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("data", []))

        # Handle pagination
        while data.get("paging", {}).get("next"):
            resp = self.session.get(data["paging"]["next"])
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("data", []))

        return results

    def get_daily_report(self, date: str) -> dict:
        """
        Pull a full daily report. Returns:
        {
            "platform": "meta",
            "date": "2026-02-12",
            "account_summary": {...},
            "campaigns": [...],
            "ad_sets": [...],
            "ads": [...],
        }
        """
        common_fields = [
            "campaign_name", "campaign_id",
            "adset_name", "adset_id",
            "ad_name", "ad_id",
            "spend", "impressions", "clicks", "cpc", "cpm", "ctr",
            "reach", "frequency",
            "actions", "action_values", "cost_per_action_type",
            "conversions", "conversion_values", "cost_per_conversion",
        ]

        # Account-level summary
        account_fields = [
            "spend", "impressions", "clicks", "cpc", "cpm", "ctr",
            "reach", "frequency",
            "actions", "action_values", "cost_per_action_type",
        ]
        logger.info(f"Pulling Meta account-level insights for {date}")
        account_data = self._insights_request("account", date, account_fields)

        # Campaign-level
        campaign_fields = [
            "campaign_name", "campaign_id",
            "spend", "impressions", "clicks", "cpc", "cpm", "ctr",
            "reach", "frequency",
            "actions", "action_values", "cost_per_action_type",
            "objective",
        ]
        logger.info("Pulling Meta campaign-level insights")
        campaign_data = self._insights_request("campaign", date, campaign_fields)

        # Ad set level
        adset_fields = [
            "campaign_name", "adset_name", "adset_id",
            "spend", "impressions", "clicks", "cpc", "cpm", "ctr",
            "reach", "frequency",
            "actions", "action_values",
        ]
        logger.info("Pulling Meta ad-set-level insights")
        adset_data = self._insights_request("adset", date, adset_fields)

        # Ad level (creative performance)
        ad_fields = [
            "campaign_name", "adset_name", "ad_name", "ad_id",
            "spend", "impressions", "clicks", "cpc", "ctr",
            "actions", "action_values",
        ]
        logger.info("Pulling Meta ad-level insights")
        ad_data = self._insights_request("ad", date, ad_fields)

        return {
            "platform": "meta",
            "date": date,
            "account_summary": account_data[0] if account_data else {},
            "campaigns": campaign_data,
            "ad_sets": adset_data,
            "ads": ad_data,
        }

    @staticmethod
    def extract_purchase_metrics(row: dict) -> dict:
        """Helper to extract purchase-specific metrics from a row."""
        purchases = 0
        purchase_value = 0.0
        cost_per_purchase = 0.0

        for action in row.get("actions", []):
            if action.get("action_type") == "purchase":
                purchases = int(action.get("value", 0))

        for av in row.get("action_values", []):
            if av.get("action_type") == "purchase":
                purchase_value = float(av.get("value", 0))

        for cpa in row.get("cost_per_action_type", []):
            if cpa.get("action_type") == "purchase":
                cost_per_purchase = float(cpa.get("value", 0))

        spend = float(row.get("spend", 0))
        roas = purchase_value / spend if spend > 0 else 0

        return {
            "purchases": purchases,
            "purchase_value": purchase_value,
            "cost_per_purchase": cost_per_purchase,
            "roas": round(roas, 2),
        }
