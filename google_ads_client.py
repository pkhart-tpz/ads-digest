"""
Google Ads API client.
Pulls campaign and ad group performance for a given day.
Uses the Google Ads REST API (v18).
"""

import requests
import logging

logger = logging.getLogger("ads-digest.google")

API_VERSION = "v23"
BASE_URL = f"https://googleads.googleapis.com/{API_VERSION}"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleAdsClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        customer_id: str,
        developer_token: str,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.customer_id = customer_id.replace("-", "")
        self.developer_token = developer_token
        self._access_token = None

    def _get_access_token(self) -> str:
        """Exchange refresh token for an access token."""
        if self._access_token:
            return self._access_token

        resp = requests.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        })
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]
        return self._access_token

    def _query(self, gaql: str) -> list[dict]:
        """Execute a GAQL query and return rows."""
        url = f"{BASE_URL}/customers/{self.customer_id}/googleAds:searchStream"
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
        }
        body = {"query": gaql}
        resp = requests.post(url, json=body, headers=headers)
        resp.raise_for_status()

        results = []
        for batch in resp.json():
            results.extend(batch.get("results", []))
        return results

    def get_daily_report(self, date: str) -> dict:
        """
        Pull a full daily report. Returns:
        {
            "platform": "google",
            "date": "2026-02-12",
            "account_summary": {...},
            "campaigns": [...],
            "ad_groups": [...],
            "ads": [...],
        }
        """
        # ── Account summary ──────────────────────────────────────
        account_query = f"""
            SELECT
                customer.descriptive_name,
                metrics.cost_micros,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.conversions,
                metrics.conversions_value,
                metrics.cost_per_conversion
            FROM customer
            WHERE segments.date = '{date}'
        """
        logger.info(f"Pulling Google Ads account summary for {date}")
        account_rows = self._query(account_query)

        # ── Campaign level ───────────────────────────────────────
        campaign_query = f"""
            SELECT
                campaign.name,
                campaign.id,
                campaign.advertising_channel_type,
                campaign.status,
                campaign.bidding_strategy_type,
                metrics.cost_micros,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.conversions,
                metrics.conversions_value,
                metrics.cost_per_conversion,
                metrics.search_impression_share
            FROM campaign
            WHERE segments.date = '{date}'
                AND campaign.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC
        """
        logger.info("Pulling Google Ads campaign-level data")
        campaign_rows = self._query(campaign_query)

        # ── Ad group level ───────────────────────────────────────
        adgroup_query = f"""
            SELECT
                campaign.name,
                ad_group.name,
                ad_group.id,
                ad_group.status,
                metrics.cost_micros,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.conversions,
                metrics.conversions_value,
                metrics.cost_per_conversion
            FROM ad_group
            WHERE segments.date = '{date}'
                AND ad_group.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC
        """
        logger.info("Pulling Google Ads ad-group-level data")
        adgroup_rows = self._query(adgroup_query)

        # ── Ad level (for creative insights) ─────────────────────
        ad_query = f"""
            SELECT
                campaign.name,
                ad_group.name,
                ad_group_ad.ad.name,
                ad_group_ad.ad.id,
                ad_group_ad.ad.type,
                ad_group_ad.ad.final_urls,
                metrics.cost_micros,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.conversions,
                metrics.conversions_value
            FROM ad_group_ad
            WHERE segments.date = '{date}'
                AND ad_group_ad.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC
            LIMIT 50
        """
        logger.info("Pulling Google Ads ad-level data")
        ad_rows = self._query(ad_query)

        return {
            "platform": "google",
            "date": date,
            "account_summary": self._parse_account(account_rows),
            "campaigns": [self._parse_campaign(r) for r in campaign_rows],
            "ad_groups": [self._parse_adgroup(r) for r in adgroup_rows],
            "ads": [self._parse_ad(r) for r in ad_rows],
        }

    @staticmethod
    def _micros_to_dollars(micros) -> float:
        return round(int(micros or 0) / 1_000_000, 2)

    def _parse_account(self, rows: list) -> dict:
        if not rows:
            return {}
        r = rows[0]
        m = r.get("metrics", {})
        spend = self._micros_to_dollars(m.get("costMicros", 0))
        conv_value = float(m.get("conversionsValue", 0))
        return {
            "spend": spend,
            "impressions": int(m.get("impressions", 0)),
            "clicks": int(m.get("clicks", 0)),
            "ctr": float(m.get("ctr", 0)),
            "avg_cpc": self._micros_to_dollars(m.get("averageCpc", 0)),
            "conversions": float(m.get("conversions", 0)),
            "conversion_value": conv_value,
            "cost_per_conversion": self._micros_to_dollars(m.get("costPerConversion", 0)),
            "roas": round(conv_value / spend, 2) if spend > 0 else 0,
        }

    def _parse_campaign(self, row: dict) -> dict:
        c = row.get("campaign", {})
        m = row.get("metrics", {})
        spend = self._micros_to_dollars(m.get("costMicros", 0))
        conv_value = float(m.get("conversionsValue", 0))
        return {
            "name": c.get("name", ""),
            "id": c.get("id", ""),
            "channel": c.get("advertisingChannelType", ""),
            "status": c.get("status", ""),
            "bidding_strategy": c.get("biddingStrategyType", ""),
            "spend": spend,
            "impressions": int(m.get("impressions", 0)),
            "clicks": int(m.get("clicks", 0)),
            "ctr": float(m.get("ctr", 0)),
            "avg_cpc": self._micros_to_dollars(m.get("averageCpc", 0)),
            "conversions": float(m.get("conversions", 0)),
            "conversion_value": conv_value,
            "cost_per_conversion": self._micros_to_dollars(m.get("costPerConversion", 0)),
            "roas": round(conv_value / spend, 2) if spend > 0 else 0,
            "impression_share": float(m.get("searchImpressionShare", 0)),
        }

    def _parse_adgroup(self, row: dict) -> dict:
        c = row.get("campaign", {})
        ag = row.get("adGroup", {})
        m = row.get("metrics", {})
        spend = self._micros_to_dollars(m.get("costMicros", 0))
        conv_value = float(m.get("conversionsValue", 0))
        return {
            "campaign_name": c.get("name", ""),
            "name": ag.get("name", ""),
            "id": ag.get("id", ""),
            "spend": spend,
            "impressions": int(m.get("impressions", 0)),
            "clicks": int(m.get("clicks", 0)),
            "ctr": float(m.get("ctr", 0)),
            "avg_cpc": self._micros_to_dollars(m.get("averageCpc", 0)),
            "conversions": float(m.get("conversions", 0)),
            "conversion_value": conv_value,
            "roas": round(conv_value / spend, 2) if spend > 0 else 0,
        }

    def _parse_ad(self, row: dict) -> dict:
        c = row.get("campaign", {})
        ag = row.get("adGroup", {})
        ad = row.get("adGroupAd", {}).get("ad", {})
        m = row.get("metrics", {})
        spend = self._micros_to_dollars(m.get("costMicros", 0))
        conv_value = float(m.get("conversionsValue", 0))
        return {
            "campaign_name": c.get("name", ""),
            "ad_group_name": ag.get("name", ""),
            "ad_name": ad.get("name", ""),
            "ad_id": ad.get("id", ""),
            "ad_type": ad.get("type", ""),
            "spend": spend,
            "impressions": int(m.get("impressions", 0)),
            "clicks": int(m.get("clicks", 0)),
            "ctr": float(m.get("ctr", 0)),
            "conversions": float(m.get("conversions", 0)),
            "conversion_value": conv_value,
            "roas": round(conv_value / spend, 2) if spend > 0 else 0,
        }
