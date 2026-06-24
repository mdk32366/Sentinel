"""
One-time seed script: adds all WGC gold-reserve countries missing from the countries table.
Run via: flyctl ssh console -a sentinel-holy-rain-4562 -C "python /app/seed_countries.py"
"""
import sys
import os
sys.path.insert(0, '/app')

from database.connection import init_db, get_session
from database.models import Country

MISSING_COUNTRIES = [
    ("AFG", "Afghanistan"),
    ("ALB", "Albania"),
    ("ARM", "Armenia"),
    ("AZE", "Azerbaijan"),
    ("BGD", "Bangladesh"),
    ("BGR", "Bulgaria"),
    ("BHR", "Bahrain"),
    ("BIH", "Bosnia and Herzegovina"),
    ("BLR", "Belarus"),
    ("BOL", "Bolivia"),
    ("CMR", "Cameroon"),
    ("CRI", "Costa Rica"),
    ("CYP", "Cyprus"),
    ("CZE", "Czechia"),
    ("DZA", "Algeria"),
    ("ECU", "Ecuador"),
    ("EST", "Estonia"),
    ("GHA", "Ghana"),
    ("GTM", "Guatemala"),
    ("HND", "Honduras"),
    ("HRV", "Croatia"),
    ("HUN", "Hungary"),
    ("IRQ", "Iraq"),
    ("ISL", "Iceland"),
    ("JOR", "Jordan"),
    ("KAZ", "Kazakhstan"),
    ("KEN", "Kenya"),
    ("KGZ", "Kyrgyzstan"),
    ("KHM", "Cambodia"),
    ("LBN", "Lebanon"),
    ("LBY", "Libya"),
    ("LKA", "Sri Lanka"),
    ("LTU", "Lithuania"),
    ("LVA", "Latvia"),
    ("MAR", "Morocco"),
    ("MKD", "North Macedonia"),
    ("MLT", "Malta"),
    ("MMR", "Myanmar"),
    ("MNG", "Mongolia"),
    ("MOZ", "Mozambique"),
    ("MUS", "Mauritius"),
    ("NGA", "Nigeria"),
    ("NIC", "Nicaragua"),
    ("NPL", "Nepal"),
    ("OMN", "Oman"),
    ("PAK", "Pakistan"),
    ("PRY", "Paraguay"),
    ("QAT", "Qatar"),
    ("ROU", "Romania"),
    ("SRB", "Serbia"),
    ("SVK", "Slovakia"),
    ("SVN", "Slovenia"),
    ("TJK", "Tajikistan"),
    ("TKM", "Turkmenistan"),
    ("TUN", "Tunisia"),
    ("UKR", "Ukraine"),
    ("URY", "Uruguay"),
    ("USA", "United States"),
    ("UZB", "Uzbekistan"),
    ("VEN", "Venezuela"),
]

def main():
    init_db()
    db = get_session()
    added = 0
    skipped = 0

    for iso_code, name in MISSING_COUNTRIES:
        exists = db.query(Country).filter_by(iso_code=iso_code).first()
        if exists:
            skipped += 1
        else:
            db.add(Country(iso_code=iso_code, name=name))
            added += 1
            print(f"  Added: {iso_code} ({name})")

    db.commit()
    db.close()
    print(f"\nDone: {added} added, {skipped} already existed")

if __name__ == "__main__":
    main()
