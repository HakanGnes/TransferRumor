"""
data_loader.py
================
api_football_data.db icindeki players + market_values tablolarini okuyup
Site2.py ve player_segmentation.py icin kullanilabilir bir DataFrame'e
cevirir.

HIBRIT MIMARI:
    - Istatistikler (mac, gol, asist, dakika, kart, rating) -> API-Football
      (fetch_api_football_data.py ile cekilir, players tablosu)
    - Piyasa degeri (VALUE) -> Transfermarkt
      (fetch_transfermarkt_values.py ile cekilir, market_values tablosu)
    - Ikisi oyuncu ismi uzerinden eslestirilir.
"""

import sqlite3
import numpy as np
import pandas as pd

DB_PATH = "api_football_data.db"

LEAGUE_NAMES = {
    39: "PREMIER LEAGUE",
    140: "LA LIGA",
    135: "SERIE A",
    78: "BUNDESLIGA",
    61: "LIGUE 1",
    88: "EREDIVISIE",
    203: "SUPER LIG",
    94: "PRIMEIRA LIGA",
    307: "SAUDI PRO LEAGUE",
    235: "RUSSIAN PREMIER LEAGUE",
    333: "UKRAINIAN PREMIER LEAGUE",
    113: "ALLSVENSKAN",
}

# API-Football pozisyonlarini projenin 3 kategorisine esler.
# Kaleciler orijinal projede de desteklenmiyordu.
POSITION_MAP = {
    "Attacker": "ATTACK",
    "Forward": "ATTACK",
    "Midfielder": "MIDFIELD",
    "Defender": "DEFENDER",
    "Goalkeeper": None,
}


def get_available_seasons(db_path: str = DB_PATH) -> list:
    """DB'de veri bulunan sezonlari (en yeniden en eskiye) dondurur."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT season FROM players ORDER BY season DESC"
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows if r[0] is not None]


def load_players(season, db_path: str = DB_PATH) -> pd.DataFrame:
    """
    Belirli bir sezon icin players + teams + market_values tablolarini
    birlestirip uppercase sutun isimleriyle dondurur.

    Donen sutunlar:
        PLAYER, CLUB, LEAGUE, NATION, AGE, POSITION, VALUE,
        APPEARANCES, MINUTES, GOALS, ASSISTS, YELLOW_CARDS, RED_CARDS, RATING
    """
    conn = sqlite3.connect(db_path)
    try:
        query = """
            SELECT
                p.name AS player, p.age, p.nationality, p.position,
                p.appearances, p.minutes, p.goals, p.assists,
                p.yellow_cards, p.red_cards, p.rating,
                p.tackles_total, p.tackles_blocks, p.tackles_interceptions,
                p.duels_total, p.duels_won,
                p.passes_total, p.passes_key,
                p.dribbles_attempts, p.dribbles_success,
                p.shots_total, p.shots_on,
                t.name AS club, t.league_id,
                mv.market_value_eur AS value
            FROM players p
            JOIN teams t ON p.team_id = t.team_id AND p.season = t.season
            LEFT JOIN market_values mv ON p.name = mv.player_name
            WHERE p.season = ? AND p.appearances IS NOT NULL
        """
        df = pd.read_sql_query(query, conn, params=(season,))
    finally:
        conn.close()

    if df.empty:
        return df

    df["position"] = df["position"].map(POSITION_MAP)
    df = df.dropna(subset=["position"])  # kaleciler ve bilinmeyenler disarida

    df["league"] = df["league_id"].map(LEAGUE_NAMES)

    df = df.rename(
        columns={
            "player": "PLAYER",
            "club": "CLUB",
            "league": "LEAGUE",
            "nationality": "NATION",
            "age": "AGE",
            "position": "POSITION",
            "value": "VALUE",
            "appearances": "APPEARANCES",
            "minutes": "MINUTES",
            "goals": "GOALS",
            "assists": "ASSISTS",
            "yellow_cards": "YELLOW_CARDS",
            "red_cards": "RED_CARDS",
            "rating": "RATING",
            "tackles_total": "TACKLES",
            "tackles_blocks": "BLOCKS",
            "tackles_interceptions": "INTERCEPTIONS",
            "duels_total": "DUELS_TOTAL",
            "duels_won": "DUELS_WON",
            "passes_total": "PASSES",
            "passes_key": "KEY_PASSES",
            "dribbles_attempts": "DRIBBLES_ATT",
            "dribbles_success": "DRIBBLES_SUCC",
            "shots_total": "SHOTS",
            "shots_on": "SHOTS_ON",
        }
    )

    df["CLUB"] = df["CLUB"].str.upper()
    df["NATION"] = df["NATION"].str.upper()

    raw_stat_cols = [
        "GOALS", "ASSISTS", "TACKLES", "BLOCKS", "INTERCEPTIONS",
        "DUELS_TOTAL", "DUELS_WON", "PASSES", "KEY_PASSES",
        "DRIBBLES_ATT", "DRIBBLES_SUCC", "SHOTS", "SHOTS_ON",
    ]
    for col in raw_stat_cols + ["AGE", "APPEARANCES", "MINUTES", "YELLOW_CARDS", "RED_CARDS", "RATING"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- 90 dakika basina oranlar ---------------------------------------
    # Ham toplamlar "cok oynayan" ile "iyi oynayan"i karistirir; kalite
    # metriklerini oynama suresine gore normalize ediyoruz. Oynama suresi
    # ve mac sayisi ayrica APPEARANCES/MINUTES olarak korunuyor (guven /
    # sureklilik sinyali olarak segmentasyonda ayrica kullaniliyor).
    nineties = (df["MINUTES"] / 90).replace(0, np.nan)
    for col in raw_stat_cols:
        df[f"{col}_P90"] = df[col] / nineties

    # Oran metrikleri (yuzde olarak anlamli olanlar)
    df["DUEL_WIN_RATE"] = df["DUELS_WON"] / df["DUELS_TOTAL"].replace(0, np.nan)
    df["DRIBBLE_SUCC_RATE"] = df["DRIBBLES_SUCC"] / df["DRIBBLES_ATT"].replace(0, np.nan)
    df["SHOT_ACCURACY"] = df["SHOTS_ON"] / df["SHOTS"].replace(0, np.nan)

    p90_cols = [f"{c}_P90" for c in raw_stat_cols]
    rate_cols = ["DUEL_WIN_RATE", "DRIBBLE_SUCC_RATE", "SHOT_ACCURACY"]

    keep_cols = (
        ["PLAYER", "CLUB", "LEAGUE", "NATION", "AGE", "POSITION", "VALUE",
         "APPEARANCES", "MINUTES", "RATING", "YELLOW_CARDS", "RED_CARDS"]
        + raw_stat_cols + p90_cols + rate_cols
    )
    df = df[keep_cols].drop_duplicates(subset=["PLAYER", "CLUB"]).reset_index(drop=True)

    # --- Eksik deger politikasi -----------------------------------------
    # Kritik ayrim: "oynadi ama istatistik kaydedilmemis" (veri boslugu)
    # ile "hic oynamadi" (gercekten uretim yok) ayni sey degil.
    #   - MINUTES > 0 ve istatistik NaN  -> veri boslugu, pozisyon medyani
    #   - MINUTES == 0                   -> uretim gercekten yok, 0
    # Hepsini medyanla doldurmak hic oynamayani sisiriyordu; hepsini 0
    # yapmak da istatistigi eksik olan gercek oyunculari cezalandiriyordu.
    df["AGE"] = pd.to_numeric(df["AGE"], errors="coerce")
    df["AGE"] = df["AGE"].fillna(df["AGE"].median())

    df["MINUTES"] = pd.to_numeric(df["MINUTES"], errors="coerce").fillna(0)
    df["APPEARANCES"] = pd.to_numeric(df["APPEARANCES"], errors="coerce").fillna(0)
    played = df["MINUTES"] > 0

    stat_cols = raw_stat_cols + p90_cols + rate_cols + ["RATING", "YELLOW_CARDS", "RED_CARDS"]
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        # pozisyon bazli medyan - forvetin tackle medyani ile defansinki
        # cok farkli, genel medyan yaniltici olurdu
        pos_median = df.groupby("POSITION")[col].transform("median")
        df[col] = df[col].where(~(played & df[col].isna()), pos_median)
        df[col] = df[col].fillna(0)

    # Cok az oynayan oyuncularda 90-dakika oranlari asiri sisebilir
    # (20 dakikada 1 gol = 4.5 gol/90). 180 dakikanin (2 tam mac) altinda
    # oynayanlarin oranlari, oynadigi sure oraninda olceklenerek gercekci
    # seviyeye cekiliyor.
    LOW_MINUTES = 180
    reliability = (df["MINUTES"] / LOW_MINUTES).clip(upper=1.0)
    for col in p90_cols + rate_cols:
        df[col] = df[col] * reliability

    # Hic oynamayanlar disiplin metriginde "hic kart gormedi" diye tam puan
    # aliyordu. Sahaya cikmayan biri disiplinli sayilmaz; bu sutunu
    # segmentasyonun notr kabul edecegi sekilde isaretliyoruz.
    df["PLAYED"] = played.astype(int)

    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")

    return df