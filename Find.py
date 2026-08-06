"""
find_league_id.py
===================
Yeni bir lig eklemeden once, o ligin API-Football'daki DOGRU ID'sini
bulmak icin kullan. Boylece TARGET_LEAGUES'e yanlis/tahmini bir ID
girip sessizce bos veri cekme riskini ortadan kaldirmis olursun.

KULLANIM:
    python find_league_id.py "Turkey"
    python find_league_id.py "Netherlands"
    python find_league_id.py "Saudi Arabia"

Her calistirma SADECE 1 API istegi harcar (gunluk 100 kotana dahil).
"""

import os
import sys
import requests

API_KEY = os.environ.get("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io"


def find_leagues_by_country(country: str):
    if not API_KEY:
        print("HATA: API_FOOTBALL_KEY ortam degiskeni ayarli degil.")
        sys.exit(1)

    resp = requests.get(
        f"{BASE_URL}/leagues",
        headers={"x-apisports-key": API_KEY},
        params={"country": country},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("errors"):
        print(f"API hatasi: {data['errors']}")
        return

    results = data.get("response", [])
    if not results:
        print(f"'{country}' icin sonuc bulunamadi. Ulke adini Ingilizce ve tam yazdigindan emin ol (orn. 'Saudi Arabia').")
        return

    print(f"\n'{country}' icin bulunan ligler:\n")
    for entry in results:
        league = entry["league"]
        # sadece "League" tipindekiler bizim projede kullandigimiz turde
        # (Cup / Super Cup gibi diger turler de listelenir, bilgi amacli)
        seasons = [s["year"] for s in entry.get("seasons", []) if s.get("year") in (2022, 2023, 2024)]
        print(f"  id={league['id']:<6} name={league['name']:<30} type={league['type']:<10} ucretsiz_planda_var_mi_sezon={seasons}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Kullanim: python find_league_id.py "Ulke Adi"')
        sys.exit(1)
    find_leagues_by_country(sys.argv[1])