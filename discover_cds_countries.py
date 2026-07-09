#!/usr/bin/env python3
"""
CDS Discovery Script - Flexible URL Handling
--------------------------------------------
Checks a wide range of countries and automatically tries both
"5-year-usd" and "5-years-usd" URL patterns.

Run: python discover_cds_countries.py
"""

import requests
import time
from typing import List, Dict, Optional

# ============================================================
# COMPREHENSIVE LIST OF COUNTRIES TO CHECK
# ============================================================
countries_to_check: List[str] = [
    # Europe
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czechia",
    "Denmark", "Estonia", "Finland", "France", "Germany", "Greece",
    "Hungary", "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg",
    "Malta", "Netherlands", "Poland", "Portugal", "Romania", "Slovakia",
    "Slovenia", "Spain", "Sweden", "Norway", "Switzerland", "United Kingdom",
    "Russia", "Ukraine", "Belarus", "Serbia",

    # Middle East & North Africa
    "Turkey", "Saudi Arabia", "United Arab Emirates", "Qatar", "Kuwait",
    "Bahrain", "Oman", "Jordan", "Lebanon", "Egypt", "Morocco", "Tunisia",
    "Algeria", "Libya", "Iraq",

    # Asia
    "China", "Japan", "South Korea", "India", "Indonesia", "Malaysia",
    "Thailand", "Philippines", "Vietnam", "Singapore", "Hong Kong",
    "Taiwan", "Pakistan", "Bangladesh", "Sri Lanka", "Cambodia",

    # Americas
    "United States", "Canada", "Mexico", "Brazil", "Argentina", "Chile",
    "Colombia", "Peru", "Uruguay", "Paraguay", "Bolivia", "Ecuador",

    # Other Markets
    "Australia", "New Zealand", "South Africa", "Nigeria", "Kenya",
    "Kazakhstan", "Uzbekistan", "Azerbaijan", "Georgia",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SentinelBot/1.0)",
}


def normalize_slug(name: str) -> str:
    """Convert country name to base slug."""
    slug = name.lower()
    slug = slug.replace(" ", "-")
    slug = slug.replace(",", "")
    slug = slug.replace(".", "")
    slug = slug.replace("'", "")
    slug = slug.replace("(", "").replace(")", "")
    slug = slug.replace(" and ", "-")
    return slug


def check_cds_url(base_slug: str, tenor: str = "5") -> Optional[str]:
    """
    Try both 'year' and 'years' variations.
    Returns the working slug if found, otherwise None.
    """
    variations = [
        f"{base_slug}-cds-{tenor}-year-usd",
        f"{base_slug}-cds-{tenor}-years-usd",
    ]

    for slug in variations:
        url = f"https://www.investing.com/rates-bonds/{slug}"
        try:
            resp = requests.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
            if resp.status_code == 200:
                return slug
        except Exception:
            continue
    return None


def discover_valid_instruments() -> Dict[str, Dict]:
    """Discover countries that have valid 5Y (and optionally 10Y) CDS pages."""
    instruments = {}

    print("🔍 Discovering sovereign CDS pages on Investing.com...\n")

    for country in countries_to_check:
        base_slug = normalize_slug(country)

        # Check 5Y
        five_y_slug = check_cds_url(base_slug, "5")
        if five_y_slug:
            print(f"✅ {country} 5Y found")
            if country not in instruments:
                instruments[country] = {}
            instruments[country]["5Y"] = {
                "slug": five_y_slug,
                "code": f"{country.upper().replace(' ', '_')}_CDS_5Y",
            }

        # Check 10Y (optional)
        ten_y_slug = check_cds_url(base_slug, "10")
        if ten_y_slug:
            print(f"✅ {country} 10Y found")
            if country not in instruments:
                instruments[country] = {}
            instruments[country]["10Y"] = {
                "slug": ten_y_slug,
                "code": f"{country.upper().replace(' ', '_')}_CDS_10Y",
            }

        time.sleep(0.3)  # Be respectful

    return instruments


if __name__ == "__main__":
    instruments = discover_valid_instruments()

    print("\n" + "=" * 65)
    print(f"✅ Total countries with at least one tenor: {len(instruments)}")
    print("=" * 65)

    if instruments:
        print("\n📋 Copy the dictionary below into your cds_fetcher.py:\n")
        print("CDS_INSTRUMENTS = {")
        for country, tenors in instruments.items():
            print(f'    "{country}": {{')
            for tenor, data in tenors.items():
                print(f'        "{tenor}": {{')
                print(f'            "slug": "{data["slug"]}",')
                print(f'            "code": "{data["code"]}",')
                print("        },")
            print("    },")
        print("}")
    else:
        print("\nNo valid CDS instruments found.")