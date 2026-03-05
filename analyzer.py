"""
AI Analyzer — sends ad + Shopify performance data to Claude for
strategic analysis, anomaly detection, and recommendations.
Now includes DoD and WoW comparison context.
"""

import json
import logging

logger = logging.getLogger("ads-digest.analyzer")

MODEL = "claude-sonnet-4-5-20250929"


class AIAnalyzer:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def analyze(
        self, meta_data: dict, google_data: dict, shopify_data: dict,
        date: str, brand: str, comparison: dict = None,
    ) -> dict:
        import anthropic

        prompt = self._build_prompt(meta_data, google_data, shopify_data, date, brand, comparison)

        client = anthropic.Anthropic(api_key=self.api_key)
        message = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = message.content[0].text

        try:
            if "```json" in raw_text:
                json_str = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                json_str = raw_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = raw_text.strip()
            analysis = json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse structured AI response, using raw text")
            analysis = {
                "executive_summary": raw_text,
                "meta_analysis": "", "google_analysis": "",
                "shopify_analysis": "", "creative_insights": "",
                "audience_insights": "", "anomalies": [],
                "recommendations": [], "budget_suggestion": "",
            }

        return analysis

    def _build_comparison_section(self, comparison: dict) -> str:
        """Build comparison data section for the prompt."""
        if not comparison:
            return "\n## COMPARISON DATA\nNo previous data available for comparison.\n"

        sections = ["\n## COMPARISON DATA (for DoD and WoW analysis)"]

        prev_day = comparison.get("prev_day")
        if prev_day:
            sections.append(f"""
### Previous Day ({comparison['prev_day_date']})
- Shopify Revenue: ${prev_day.get('shopify_revenue', 0):,.2f}
- Orders: {prev_day.get('shopify_orders', 0)}
- AOV: ${prev_day.get('shopify_aov', 0):.2f}
- Total Ad Spend: ${prev_day.get('total_spend', 0):,.2f}
- Meta Spend: ${prev_day.get('meta_spend', 0):,.2f} | ROAS: {prev_day.get('meta_roas', 0)}x
- Google Spend: ${prev_day.get('google_spend', 0):,.2f} | ROAS: {prev_day.get('google_roas', 0)}x
- New Customer Rate: {prev_day.get('shopify_new_customer_rate', 0)}%""")
        else:
            sections.append(f"\n### Previous Day ({comparison['prev_day_date']})\nNo data available.")

        prev_week = comparison.get("prev_week")
        if prev_week:
            sections.append(f"""
### Same Day Last Week ({comparison['prev_week_date']})
- Shopify Revenue: ${prev_week.get('shopify_revenue', 0):,.2f}
- Orders: {prev_week.get('shopify_orders', 0)}
- AOV: ${prev_week.get('shopify_aov', 0):.2f}
- Total Ad Spend: ${prev_week.get('total_spend', 0):,.2f}
- Meta Spend: ${prev_week.get('meta_spend', 0):,.2f} | ROAS: {prev_week.get('meta_roas', 0)}x
- Google Spend: ${prev_week.get('google_spend', 0):,.2f} | ROAS: {prev_week.get('google_roas', 0)}x
- New Customer Rate: {prev_week.get('shopify_new_customer_rate', 0)}%""")
        else:
            sections.append(f"\n### Same Day Last Week ({comparison['prev_week_date']})\nNo data available.")

        return "\n".join(sections)

    def _build_prompt(
        self, meta_data: dict, google_data: dict, shopify_data: dict,
        date: str, brand: str, comparison: dict = None,
    ) -> str:
        comparison_section = self._build_comparison_section(comparison)

        return f"""You are a senior performance marketing analyst for {brand}, a direct-to-consumer CPG brand. Analyze the following daily performance data from all three sources and provide strategic insights.

IMPORTANT: Shopify is the SOURCE OF TRUTH for actual revenue. Ad platforms (Meta/Google) often over-count conversions because they both try to take credit for the same sale. Always compare what the ad platforms claim vs what Shopify actually recorded.

IMPORTANT: When comparison data is available, include Day-over-Day (DoD) and Week-over-Week (WoW) trend analysis throughout your insights. Call out significant movements with percentage changes.

## Date: {date}

## META (FACEBOOK/INSTAGRAM) ADS DATA
```json
{json.dumps(meta_data, indent=2, default=str)}
```

## GOOGLE ADS DATA
```json
{json.dumps(google_data, indent=2, default=str)}
```

## SHOPIFY DATA (SOURCE OF TRUTH)
```json
{json.dumps(shopify_data, indent=2, default=str)}
```
{comparison_section}

Provide your analysis as a JSON object with EXACTLY these keys:

{{
    "executive_summary": "2-3 sentence overview. Use Shopify revenue as the real number. Mention true blended ROAS (Shopify revenue / total ad spend). Include DoD and WoW revenue/ROAS changes if comparison data is available. Flag if ad platforms are significantly over-reporting.",

    "meta_analysis": "Meta ads performance. Spend efficiency, ROAS by campaign, CPM trends, over/under-performers. Note DoD/WoW changes in spend and ROAS if comparison data available.",

    "google_analysis": "Google Ads performance. Search impression share, CPC trends, conversion rates, campaign-level performance. Note DoD/WoW changes if comparison data available.",

    "shopify_analysis": "Shopify store health. Orders, AOV trends, new vs returning customer mix, top products, discount code impact on margins. Include DoD/WoW order and revenue trends.",

    "creative_insights": "Which ad creatives/formats are performing best and worst. Creative fatigue signals.",

    "audience_insights": "Audience/targeting performance. Which are most efficient? Scale or cut recommendations.",

    "attribution_gap": "Compare what Meta + Google claim in conversions/revenue vs what Shopify actually shows. How big is the gap? What does this mean for how we evaluate campaigns?",

    "anomalies": ["List of unusual patterns, spikes, drops, or data quality issues. Especially note significant DoD or WoW deviations."],

    "recommendations": [
        {{
            "priority": "HIGH/MEDIUM/LOW",
            "action": "Specific, actionable recommendation",
            "rationale": "Why this matters and expected impact"
        }}
    ],

    "budget_suggestion": "Based on TRUE Shopify ROAS (not platform-reported) and DoD/WoW trends, should total daily spend increase, decrease, or stay the same? Specific reallocation suggestions between platforms and campaigns."
}}

Be specific, data-driven, and action-oriented. Reference actual numbers and percentage changes. Prioritize by ROAS impact. Return ONLY the JSON object."""
