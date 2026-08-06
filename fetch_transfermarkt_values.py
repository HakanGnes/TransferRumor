"""
fetch_transfermarkt_values.py
===============================
api_football_data.db'deki oyuncular icin, ismen eslestirerek
transfermarkt-api (https://transfermarkt-api.fly.dev, felipeall/transfermarkt-api
projesinin herkese acik host edilen sürümü) uzerinden piyasa degeri (market
value) ceker ve ayni DB icinde yeni bir 'market_values' tablosuna kaydeder.

ONEMLI - RISKLER VE SINIRLAR:
    1. Bu API resmi degil; Transfermarkt sayfalarini scrape ediyor. Kisisel/
       egitim amacli kullanim yaygin ama Transfermarkt'in kullanim sartlarina
       aykiri olabilir.
    2. Isim eslestirme TAM DEGIL: API-Football'daki isim ile Transfermarkt'taki
       isim birebir ayni olmayabilir (orn. "Kevin De Bruyne" vs "K. De Bruyne").
       Bu yuzden her eslestirme confidence="name_only" olarak isaretleniyor;
       KRITIK kararlar icin (orn. yayinlanacak bir rapor) sonuclari gozden
       gecirmen onerilir.
    3. Herkese acik instance rate-limitli (varsayilan ~2 istek/3sn). Bu yuzden
       istekler arasi bilerek yavas tutuluyor. Cok sayida oyuncu icin script
       uzun surebilir (birkac bin oyuncu icin ~30-60 dakika); bu normaldir.
    4. Gunluk sabit bir kota YOK (API-Football'daki gibi), sadece ani istek
       hizi sinirlaniyor. Yine de script kesintiye ugrarsa kaldigi yerden
       devam eder (zaten islenmis oyuncular atlanir).

KULLANIM
--------
    python fetch_transfermarkt_values.py
"""

import re
import sqlite3
import sys
import time
import urllib.parse

import requests

# Windows konsolunda bazi Turkce/ozel karakterler print() sirasinda
# UnicodeEncodeError'a (ve bazi terminal/IDE kombinasyonlarinda scriptin
# sessizce takilmasina) sebep olabiliyor. Stdout'u acikca UTF-8'e zorluyoruz;
# hala kod sayfasi desteklemeyen bir karakter gelirse HATA VERMEK yerine
# '?' ile degistirilsin (errors='replace') ki script asla bu yuzden donmasin.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "api_football_data.db"
# ONCEDEN: "https://transfermarkt-api.fly.dev" (herkese acik, kararsiz test instance'i)
# ARTIK: kendi bilgisayarinda Docker ile calisan self-hosted instance
BASE_URL = "http://localhost:8000"
REQUEST_DELAY_SECONDS = 1.2  # self-hosted oldugu icin kisaltildi, ama scraper
                              # yine de gercek transfermarkt.com'u ziyaret ediyor
                              # -- IP banlanmasin diye hala makul bir bekleme birakildi


# --------------------------------------------------------------------------
# VERITABANI
# --------------------------------------------------------------------------

def init_market_values_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_values (
            player_name TEXT PRIMARY KEY,   -- api_football_data.db'deki players.name ile birebir eslesir
            transfermarkt_id TEXT,
            transfermarkt_name TEXT,        -- Transfermarkt'ta eslesen isim (kontrol icin)
            market_value_eur REAL,          -- Euro cinsinden sayisal deger (parse edilmis)
            match_confidence TEXT,          -- 'name_only' | 'not_found' | 'timeout' | 'error'
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def get_unfetched_players(conn: sqlite3.Connection) -> list:
    """
    (player_name, search_name) ciftlerini dondurur:
      - player_name: players.name (market_values ile eslesme/kayit anahtari,
        DEGISTIRILMEZ - data_loader.py bununla JOIN yapiyor)
      - search_name: firstname+lastname varsa TAM isim (Transfermarkt'ta
        daha iyi eslesir, orn. 'Sofyan Amrabat'), yoksa players.name'e
        (orn. 'S. Amrabat') geri duser
    """
    has_names = conn.execute(
        "SELECT COUNT(*) FROM pragma_table_info('players') WHERE name IN ('firstname','lastname')"
    ).fetchone()[0]

    if has_names == 2:
        query = """
            SELECT DISTINCT p.name,
                   CASE
                       WHEN TRIM(COALESCE(p.firstname,'') || ' ' || COALESCE(p.lastname,'')) != ''
                       THEN TRIM(COALESCE(p.firstname,'') || ' ' || COALESCE(p.lastname,''))
                       ELSE p.name
                   END AS search_name
            FROM players p
            LEFT JOIN market_values mv ON p.name = mv.player_name
            WHERE mv.player_name IS NULL
        """
    else:
        query = """
            SELECT DISTINCT p.name, p.name AS search_name
            FROM players p
            LEFT JOIN market_values mv ON p.name = mv.player_name
            WHERE mv.player_name IS NULL
        """
    rows = conn.execute(query).fetchall()
    return [(r[0], r[1]) for r in rows if r[0]]


# --------------------------------------------------------------------------
# DEGER PARSE ETME ("€180.00m" -> 180000000.0)
# --------------------------------------------------------------------------

def parse_market_value(raw_value) -> float | None:
    """
    Transfermarkt'in dondurdugu deger stringini (orn. '€180.00m', '€500k',
    '€45.5m', ya da zaten sayisal bir deger) Euro cinsinden float'a cevirir.
    Anlasilamayan formatlarda None doner (crash etmez).
    """
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        return float(raw_value)

    s = str(raw_value).strip()
    match = re.search(r"([\d.,]+)\s*([mk])?", s, re.IGNORECASE)
    if not match:
        return None

    number_part = match.group(1).replace(",", ".")
    suffix = (match.group(2) or "").lower()
    try:
        number = float(number_part)
    except ValueError:
        return None

    if suffix == "m":
        return number * 1_000_000
    if suffix == "k":
        return number * 1_000
    return number


# --------------------------------------------------------------------------
# API ISTEMCISI
# --------------------------------------------------------------------------

class TransfermarktClient:
    MAX_429_RETRIES = 3
    MAX_CONSECUTIVE_FAILURES = 15  # bu kadar ust uste hata olursa servis muhtemelen down

    def __init__(self):
        self.session = requests.Session()
        self._last_request_time = 0.0
        self.consecutive_failures = 0

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_time
        wait = REQUEST_DELAY_SECONDS - elapsed
        if wait > 0:
            time.sleep(wait)

    def _get(self, path: str, params: dict = None, _retry_count: int = 0) -> dict | None:
        self._throttle()
        try:
            # (connect_timeout, read_timeout) - okuma asamasinda sonsuza kadar
            # beklemeyi engeller, DNS/baglanti asamasi da ayri sinirlandirilir.
            resp = self.session.get(f"{BASE_URL}{path}", params=params or {}, timeout=(10, 20))
        except requests.RequestException as e:
            print(f"    [AG HATASI] {e}")
            self._last_request_time = time.monotonic()
            self._register_failure()
            return None
        self._last_request_time = time.monotonic()

        if resp.status_code == 429:
            if _retry_count >= self.MAX_429_RETRIES:
                print(f"    [RATE LIMIT] {self.MAX_429_RETRIES} denemeden sonra hala 429, bu oyuncu atlaniyor.")
                self._register_failure()
                return None
            print(f"    [RATE LIMIT] 429 alindi, 10sn bekleniyor... (deneme {_retry_count + 1}/{self.MAX_429_RETRIES})")
            time.sleep(10)
            return self._get(path, params, _retry_count=_retry_count + 1)

        if resp.status_code != 200:
            print(f"    [HTTP {resp.status_code}] {path}")
            self._register_failure()
            return None

        self.consecutive_failures = 0  # basarili istek, sayaci sifirla
        try:
            return resp.json()
        except ValueError:
            print(f"    [JSON HATASI] cevap parse edilemedi: {resp.text[:200]}")
            return None

    def _register_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            print(
                f"\n[UYARI] Ust uste {self.consecutive_failures} istek basarisiz oldu. "
                f"Transfermarkt-api servisi su an calismiyor olabilir "
                f"(https://transfermarkt-api.fly.dev/docs adresini tarayicida acip kontrol et). "
                f"60 saniye bekleyip devam edilecek..."
            )
            time.sleep(60)
            self.consecutive_failures = 0

    def search_player(self, name: str) -> dict | None:
        """Isme gore arar, ilk sonucu doner (varsa)."""
        encoded_name = urllib.parse.quote(name)
        data = self._get(f"/players/search/{encoded_name}", params={"page_number": 1})
        if not data:
            return None
        results = data.get("results", [])
        return results[0] if results else None

    def get_player_profile(self, player_id: str) -> dict | None:
        return self._get(f"/players/{player_id}/profile")


# --------------------------------------------------------------------------
# ANA AKIS
# --------------------------------------------------------------------------

def main():
    conn = sqlite3.connect(DB_PATH)
    init_market_values_table(conn)

    players = get_unfetched_players(conn)
    print(f"Islenecek oyuncu sayisi: {len(players)}", flush=True)
    if not players:
        print("Tum oyuncular icin piyasa degeri zaten cekilmis.", flush=True)
        return

    client = TransfermarktClient()
    first_result_shown = False

    for i, (player_name, search_name) in enumerate(players, start=1):
        label = player_name if player_name == search_name else f"{player_name} (aranan: {search_name})"
        print(f"[{i}/{len(players)}] {label}", flush=True)

        try:
            search_result = client.search_player(search_name)
        except Exception as e:
            print(f"    [BEKLENMEYEN HATA] {type(e).__name__}: {e}", flush=True)
            conn.execute(
                "INSERT OR REPLACE INTO market_values (player_name, match_confidence) VALUES (?, 'error')",
                (player_name,),
            )
            conn.commit()
            continue

        if not first_result_shown and search_result:
            print(f"    [ORNEK HAM CEVAP] {search_result}", flush=True)
            first_result_shown = True

        if not search_result:
            conn.execute(
                "INSERT OR REPLACE INTO market_values (player_name, match_confidence) VALUES (?, 'not_found')",
                (player_name,),
            )
            conn.commit()
            continue

        tm_id = search_result.get("id")
        tm_name = search_result.get("name")
        raw_value = search_result.get("marketValue")

        if raw_value is None and tm_id:
            profile = client.get_player_profile(tm_id)
            if profile:
                raw_value = profile.get("marketValue") or profile.get("marketValueDetails", {}).get("current")

        value_eur = parse_market_value(raw_value)

        conn.execute(
            """
            INSERT OR REPLACE INTO market_values
            (player_name, transfermarkt_id, transfermarkt_name, market_value_eur, match_confidence)
            VALUES (?, ?, ?, ?, 'name_only')
            """,
            (player_name, tm_id, tm_name, value_eur),
        )
        conn.commit()

        print(f"    -> {tm_name} | {value_eur}", flush=True)

    print("\nTamamlandi.", flush=True)


if __name__ == "__main__":
    main()