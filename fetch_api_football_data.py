"""
fetch_api_football_data.py
============================
API-Football (v3.football.api-sports.io) ucretsiz planindan oyuncu/takim
verisi cekip yerel bir SQLite veritabanina kaydeden script.

UCRETSIZ PLAN LIMITLERI (2026 itibariyle):
    - Gunde 100 istek (UTC 00:00'da sifirlanir)
    - Dakikada 10 istek
Bu script her iki limite de otomatik uyar ve gunluk kota bittiginde
kaldigi yerde durur; bir sonraki calistirmada kaldigi yerden devam eder.

KURULUM
-------
1) https://www.api-football.com adresinden ucretsiz hesap ac, API key al.
2) API key'i ortam degiskeni olarak ayarla (kod icine YAZMA):
   Windows (PowerShell):  $env:API_FOOTBALL_KEY = "senin_keyin"
   Windows (cmd):         set API_FOOTBALL_KEY=senin_keyin
   Mac/Linux:             export API_FOOTBALL_KEY="senin_keyin"
3) pip install requests
4) python fetch_api_football_data.py

KULLANIM
--------
Varsayilan olarak asagidaki TARGET_LEAGUES listesindeki ligler icin
tum takimlari ve oyuncu istatistiklerini ceker. SEASON degiskenini
kendi ihtiyacina gore guncelle (API-Football'da sezon, sezonun basladigi
yili ifade eder; ornegin 2025-26 sezonu icin season=2025).

Script calistikca DB dosyasi (api_football_data.db) buyur; ayni scripti
her gun tekrar calistirdiginda otomatik olarak eksik kalan takim/oyuncu
verisini cekmeye devam eder, zaten cekilmis olani tekrar cekmez.
"""

import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests

# --------------------------------------------------------------------------
# AYARLAR
# --------------------------------------------------------------------------

API_KEY = os.environ.get("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io"
DB_PATH = "api_football_data.db"

# API-Football lig ID'leri (sabit, degismez).
# Yeni bir lig eklemeden once find_league_id.py ile ID'yi DOGRULA.
TARGET_LEAGUES = {
    39: "Premier League",
    140: "La Liga",
    135: "Serie A",
    78: "Bundesliga",
    61: "Ligue 1",
    # --- asagidakileri find_league_id.py ciktisina gore duzelt ---
    88: "Eredivisie",          # Hollanda (teyit et)
    203: "Super Lig",          # Turkiye (teyit et)
    94: "Primeira Liga",       # Portekiz (teyit et)
    307: "Saudi Pro League",   # Suudi Arabistan (teyit et)
    235: "Russian Premier League",  # Rusya (teyit et)
    333: "Ukrainian Premier League",  # Ukrayna (teyit et)
    113: "Allsvenskan",        # Isvec (teyit et)
}
SEASON = 2024  # UCRETSIZ PLAN SADECE 2022-2024 SEZONLARINA IZIN VERIYOR.
                # 2024 -> 2024-25 sezonu (tamamlanmis, en guncel izinli sezon).
                # Farkli bir sezon denemek istersen 2022/2023/2024 disinda bir
                # deger API'den "Free plans do not have access to this season"
                # hatasi doner.

FREE_PLAN_DAILY_LIMIT = 100
FREE_PLAN_MIN_INTERVAL_SECONDS = 6.5  # dakikada 10 istek -> istek basi >=6sn

# --------------------------------------------------------------------------
# VERITABANI
# --------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS teams (
            team_id INTEGER PRIMARY KEY,
            league_id INTEGER,
            season INTEGER,
            name TEXT,
            country TEXT,
            fetched_players INTEGER DEFAULT 0  -- 1 = bu takimin oyunculari cekildi
        );

        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER,
            season INTEGER,
            team_id INTEGER,
            name TEXT,
            firstname TEXT,
            lastname TEXT,
            age INTEGER,
            nationality TEXT,
            position TEXT,
            appearances INTEGER,
            minutes INTEGER,
            goals INTEGER,
            assists INTEGER,
            yellow_cards INTEGER,
            red_cards INTEGER,
            rating REAL,
            raw_json TEXT,               -- API'den donen tam JSON (ileride yeni alan lazim olursa)
            PRIMARY KEY (player_id, season, team_id)
        );

        CREATE TABLE IF NOT EXISTS api_usage (
            usage_date TEXT PRIMARY KEY,   -- 'YYYY-MM-DD' (UTC)
            requests_used INTEGER DEFAULT 0
        );
        """
    )
    conn.commit()


def get_today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_requests_used_today(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT requests_used FROM api_usage WHERE usage_date = ?", (get_today_key(),)
    ).fetchone()
    return row[0] if row else 0


def increment_requests_used(conn: sqlite3.Connection) -> None:
    today = get_today_key()
    conn.execute(
        """
        INSERT INTO api_usage (usage_date, requests_used) VALUES (?, 1)
        ON CONFLICT(usage_date) DO UPDATE SET requests_used = requests_used + 1
        """,
        (today,),
    )
    conn.commit()


# --------------------------------------------------------------------------
# API ISTEMCISI (rate-limit + gunluk kota bilincli)
# --------------------------------------------------------------------------

class QuotaExceeded(Exception):
    """Gunluk ucretsiz kota (100 istek) doldugunda firlatilir."""


class ApiFootballClient:
    def __init__(self, conn: sqlite3.Connection):
        if not API_KEY:
            raise RuntimeError(
                "API_FOOTBALL_KEY ortam degiskeni bulunamadi. "
                "Once API key'ini ortam degiskeni olarak ayarla (bkz. dosya basindaki aciklama)."
            )
        self.conn = conn
        self.session = requests.Session()
        self.session.headers.update({"x-apisports-key": API_KEY})
        self._last_request_time = 0.0

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        wait = FREE_PLAN_MIN_INTERVAL_SECONDS - elapsed
        if wait > 0:
            time.sleep(wait)

    def get(self, endpoint: str, params: dict) -> dict:
        used = get_requests_used_today(self.conn)
        if used >= FREE_PLAN_DAILY_LIMIT:
            raise QuotaExceeded(
                f"Gunluk ucretsiz kota ({FREE_PLAN_DAILY_LIMIT} istek) doldu. "
                f"Yarin (UTC 00:00 sonrasi) scripti tekrar calistir."
            )

        self._respect_rate_limit()
        url = f"{BASE_URL}/{endpoint}"
        resp = self.session.get(url, params=params, timeout=30)
        self._last_request_time = time.monotonic()
        increment_requests_used(self.conn)

        if resp.status_code == 429:
            raise QuotaExceeded("API 429 dondurdu (rate limit). Kota bitmis olabilir.")
        resp.raise_for_status()

        data = resp.json()
        if data.get("errors"):
            print(f"  [UYARI] API hata dondurdu: {data['errors']}")
        return data


# --------------------------------------------------------------------------
# FETCH FONKSIYONLARI
# --------------------------------------------------------------------------

def fetch_teams_for_league(client: ApiFootballClient, conn: sqlite3.Connection, league_id: int, season: int) -> None:
    existing = conn.execute(
        "SELECT COUNT(*) FROM teams WHERE league_id = ? AND season = ?", (league_id, season)
    ).fetchone()[0]
    if existing > 0:
        print(f"  Takimlar zaten cekilmis (league={league_id}, season={season}), atlaniyor.")
        return

    print(f"  Takimlar cekiliyor: league={league_id}, season={season}")
    data = client.get("teams", {"league": league_id, "season": season})

    for entry in data.get("response", []):
        team = entry["team"]
        conn.execute(
            """
            INSERT OR IGNORE INTO teams (team_id, league_id, season, name, country, fetched_players)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (team["id"], league_id, season, team["name"], team.get("country")),
        )
    conn.commit()
    print(f"  {len(data.get('response', []))} takim kaydedildi.")


def flatten_player_entry(entry: dict, season: int, team_id: int) -> tuple:
    """API'nin /players cevabindaki tek bir oyuncu kaydini duz bir tuple'a cevirir."""
    player = entry["player"]
    # statistics bir liste; ilgili takim/sezon icin olani sec (genelde tek eleman)
    stats_list = entry.get("statistics", [])
    stats = stats_list[0] if stats_list else {}

    games = stats.get("games", {}) or {}
    goals = stats.get("goals", {}) or {}
    cards = stats.get("cards", {}) or {}

    import json

    return (
        player["id"],
        season,
        team_id,
        player.get("name"),
        player.get("firstname"),
        player.get("lastname"),
        player.get("age"),
        player.get("nationality"),
        games.get("position"),
        games.get("appearences"),
        games.get("minutes"),
        goals.get("total"),
        goals.get("assists"),
        cards.get("yellow"),
        cards.get("red"),
        games.get("rating"),
        json.dumps(entry, ensure_ascii=False),
    )


def fetch_players_for_team(client: ApiFootballClient, conn: sqlite3.Connection, team_id: int, season: int) -> None:
    already = conn.execute(
        "SELECT fetched_players FROM teams WHERE team_id = ? AND season = ?", (team_id, season)
    ).fetchone()
    if already and already[0] == 1:
        return  # bu takim icin zaten cekilmis

    page = 1
    total_players = 0
    while True:
        print(f"    /players team={team_id} season={season} page={page}")
        data = client.get("players", {"team": team_id, "season": season, "page": page})

        for entry in data.get("response", []):
            row = flatten_player_entry(entry, season, team_id)
            conn.execute(
                """
                INSERT OR REPLACE INTO players
                (player_id, season, team_id, name, firstname, lastname, age, nationality, position,
                 appearances, minutes, goals, assists, yellow_cards, red_cards, rating, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            total_players += 1
        conn.commit()

        paging = data.get("paging", {})
        if paging.get("current", 1) >= paging.get("total", 1):
            break
        page += 1

    conn.execute(
        "UPDATE teams SET fetched_players = 1 WHERE team_id = ? AND season = ?", (team_id, season)
    )
    conn.commit()
    print(f"    -> {total_players} oyuncu kaydi kaydedildi (team={team_id}).")


# --------------------------------------------------------------------------
# ANA AKIS
# --------------------------------------------------------------------------

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    try:
        client = ApiFootballClient(conn)
    except RuntimeError as e:
        print(f"HATA: {e}")
        sys.exit(1)

    used = get_requests_used_today(conn)
    print(f"Bugun simdiye kadar kullanilan istek: {used}/{FREE_PLAN_DAILY_LIMIT}")

    try:
        for league_id, league_name in TARGET_LEAGUES.items():
            print(f"\n=== {league_name} (id={league_id}) ===")
            fetch_teams_for_league(client, conn, league_id, SEASON)

            team_count = conn.execute(
                "SELECT COUNT(*) FROM teams WHERE league_id = ? AND season = ?",
                (league_id, SEASON),
            ).fetchone()[0]
            if team_count == 0:
                print("  Bu lig icin takim verisi alinamadi (yukaridaki UYARI mesajina bak), atlaniyor.")
                continue

            teams = conn.execute(
                "SELECT team_id, name FROM teams WHERE league_id = ? AND season = ? AND fetched_players = 0",
                (league_id, SEASON),
            ).fetchall()

            if not teams:
                print("  Bu ligin tum takimlarinin oyuncu verisi zaten cekilmis.")
                continue

            for team_id, team_name in teams:
                print(f"  -> {team_name}")
                fetch_players_for_team(client, conn, team_id, SEASON)

    except QuotaExceeded as e:
        print(f"\n[DURDU] {e}")
        print("Simdiye kadar cekilen veri DB'de guvende. Scripti yarin tekrar calistir.")
        sys.exit(0)

    print("\nTum hedef ligler icin veri cekme tamamlandi.")


if __name__ == "__main__":
    main()