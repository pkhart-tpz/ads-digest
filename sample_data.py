"""
Sample data for testing the digest pipeline without live API credentials.
"""


def get_sample_data():
    meta_data = {
        "platform": "meta",
        "date": "2026-02-12",
        "account_summary": {
            "spend": "847.32",
            "impressions": "124532",
            "clicks": "2847",
            "cpc": "0.30",
            "cpm": "6.80",
            "ctr": "2.29",
            "reach": "89421",
            "frequency": "1.39",
            "actions": [
                {"action_type": "purchase", "value": "47"},
                {"action_type": "add_to_cart", "value": "312"},
                {"action_type": "view_content", "value": "1893"},
            ],
            "action_values": [
                {"action_type": "purchase", "value": "3412.80"},
            ],
            "cost_per_action_type": [
                {"action_type": "purchase", "value": "18.03"},
            ],
        },
        "campaigns": [
            {
                "campaign_name": "SMBL - Prospecting - Broad",
                "campaign_id": "120001",
                "spend": "412.50", "impressions": "68432", "clicks": "1523",
                "ctr": "2.22", "cpc": "0.27", "cpm": "6.03",
                "reach": "52341", "frequency": "1.31",
                "objective": "OUTCOME_SALES",
                "actions": [{"action_type": "purchase", "value": "22"}],
                "action_values": [{"action_type": "purchase", "value": "1628.00"}],
                "cost_per_action_type": [{"action_type": "purchase", "value": "18.75"}],
            },
            {
                "campaign_name": "SMBL - Retargeting - DPA",
                "campaign_id": "120002",
                "spend": "234.82", "impressions": "31200", "clicks": "842",
                "ctr": "2.70", "cpc": "0.28", "cpm": "7.53",
                "reach": "21340", "frequency": "1.46",
                "objective": "OUTCOME_SALES",
                "actions": [{"action_type": "purchase", "value": "19"}],
                "action_values": [{"action_type": "purchase", "value": "1432.80"}],
                "cost_per_action_type": [{"action_type": "purchase", "value": "12.36"}],
            },
            {
                "campaign_name": "SMBL - TOF - UGC Video",
                "campaign_id": "120003",
                "spend": "200.00", "impressions": "24900", "clicks": "482",
                "ctr": "1.94", "cpc": "0.41", "cpm": "8.03",
                "reach": "15740", "frequency": "1.58",
                "objective": "OUTCOME_SALES",
                "actions": [{"action_type": "purchase", "value": "6"}],
                "action_values": [{"action_type": "purchase", "value": "352.00"}],
                "cost_per_action_type": [{"action_type": "purchase", "value": "33.33"}],
            },
        ],
        "ad_sets": [],
        "ads": [],
    }

    google_data = {
        "platform": "google",
        "date": "2026-02-12",
        "account_summary": {
            "spend": 423.17,
            "impressions": 18743,
            "clicks": 1247,
            "ctr": 0.0665,
            "avg_cpc": 0.34,
            "conversions": 31.0,
            "conversion_value": 2108.40,
            "cost_per_conversion": 13.65,
            "roas": 4.98,
        },
        "campaigns": [
            {
                "name": "SMBL - Brand Search", "id": "200001",
                "channel": "SEARCH", "status": "ENABLED",
                "bidding_strategy": "TARGET_ROAS",
                "spend": 89.42, "impressions": 3241, "clicks": 487,
                "ctr": 0.1503, "avg_cpc": 0.18, "conversions": 18.0,
                "conversion_value": 1296.00, "cost_per_conversion": 4.97,
                "roas": 14.49, "impression_share": 0.87,
            },
            {
                "name": "SMBL - Non-Brand Search", "id": "200002",
                "channel": "SEARCH", "status": "ENABLED",
                "bidding_strategy": "MAXIMIZE_CONVERSIONS",
                "spend": 198.50, "impressions": 8432, "clicks": 512,
                "ctr": 0.0607, "avg_cpc": 0.39, "conversions": 8.0,
                "conversion_value": 512.40, "cost_per_conversion": 24.81,
                "roas": 2.58, "impression_share": 0.34,
            },
            {
                "name": "SMBL - Performance Max", "id": "200003",
                "channel": "PERFORMANCE_MAX", "status": "ENABLED",
                "bidding_strategy": "MAXIMIZE_CONVERSION_VALUE",
                "spend": 135.25, "impressions": 7070, "clicks": 248,
                "ctr": 0.0351, "avg_cpc": 0.55, "conversions": 5.0,
                "conversion_value": 300.00, "cost_per_conversion": 27.05,
                "roas": 2.22, "impression_share": 0.0,
            },
        ],
        "ad_groups": [],
        "ads": [],
    }

    shopify_data = {
        "platform": "shopify",
        "date": "2026-02-12",
        "summary": {
            "total_orders": 58,
            "total_revenue": 4387.42,
            "total_refunds": 89.99,
            "net_revenue": 4297.43,
            "average_order_value": 74.09,
            "total_units_sold": 83,
            "total_discount_amount": 312.50,
            "new_customers": 34,
            "returning_customers": 24,
            "new_customer_rate": 58.6,
        },
        "top_products": [
            {"name": "SMBL Daily Focus Capsules", "units": 28, "revenue": 1679.72},
            {"name": "SMBL Night Recovery Blend", "units": 19, "revenue": 1139.81},
            {"name": "SMBL Starter Kit", "units": 14, "revenue": 979.86},
            {"name": "SMBL Energy+ Powder", "units": 12, "revenue": 419.88},
            {"name": "SMBL Calm Gummies", "units": 10, "revenue": 299.90},
        ],
        "discount_codes": {
            "WELCOME15": {"uses": 12, "total_discount": 134.28},
            "BUNDLE20": {"uses": 6, "total_discount": 107.94},
            "VALENTINES": {"uses": 4, "total_discount": 70.28},
        },
        "hourly_orders": [
            {"hour": "06", "count": 2}, {"hour": "07", "count": 3},
            {"hour": "08", "count": 5}, {"hour": "09", "count": 7},
            {"hour": "10", "count": 8}, {"hour": "11", "count": 6},
            {"hour": "12", "count": 4}, {"hour": "13", "count": 3},
            {"hour": "14", "count": 2}, {"hour": "15", "count": 2},
            {"hour": "16", "count": 3}, {"hour": "17", "count": 2},
            {"hour": "18", "count": 1}, {"hour": "19", "count": 3},
            {"hour": "20", "count": 4}, {"hour": "21", "count": 2},
            {"hour": "22", "count": 1},
        ],
        "inventory_alerts": [
            {"product": "SMBL Daily Focus Capsules", "variant": "60ct", "sku": "SMBL-DFC-60", "quantity_remaining": 7},
            {"product": "SMBL Starter Kit", "variant": "Default", "sku": "SMBL-SK-01", "quantity_remaining": 4},
        ],
        "orders": [],
    }

    return meta_data, google_data, shopify_data
