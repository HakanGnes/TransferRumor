"""
reset_market_values.py
========================
api_football_data.db icindeki market_values tablosunu TAMAMEN temizler.

NEDEN GEREKLI:
    Piyasa degerleri ilk toplandiginda oyuncular KISALTILMIS isimle
    (orn. "M. de Ligt") aranmisti ve arama sonucunun ILK kaydi alinmisti.
    Bu bazen tamamen baska bir oyuncuyla eslesti:
        "M. de Ligt" -> "Max de Ligt"   (dogrusu: Matthijs de Ligt, ~40M EUR)
        "T. Müller"  -> "Tim Müller"    (dogrusu: Thomas Müller)

    Artik players tablosunda firstname/lastname sutunlari var ve
    fetch_transfermarkt_values.py aramayi TAM ISIMLE yapiyor. Bu yuzden
    tabloyu sifirlayip bastan cekmek en temiz cozum.

DIKKAT: players / teams tablolarina DOKUNMAZ, sadece market_values silinir.
        API-Football istatistik verilerin guvende.

KULLANIM:
    python reset_market_values.py
    # sonra:
    docker start transfermarkt-api
    python fetch_transfermarkt_values.py
"""

import sqlite3

DB_PATH = "api_football_data.db"


def main():
    conn = sqlite3.connect(DB_PATH)

    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='market_values'"
    ).fetchone()
    if not exists:
        print("market_values tablosu zaten yok - yapilacak bir sey yok.")
        print("Dogrudan fetch_transfermarkt_values.py calistirabilirsin.")
        return

    count = conn.execute("SELECT COUNT(*) FROM market_values").fetchone()[0]
    with_value = conn.execute(
        "SELECT COUNT(*) FROM market_values WHERE market_value_eur IS NOT NULL"
    ).fetchone()[0]

    print(f"Silinecek kayit: {count} (bunlarin {with_value} tanesinde deger dolu)")

    conn.execute("DELETE FROM market_values")
    conn.commit()

    # Diger tablolarin etkilenmedigini dogrula
    players = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]

    print("\nmarket_values temizlendi.")
    print(f"Dokunulmayan veriler: players={players}, teams={teams}")
    print("\nSimdi sirasiyla:")
    print("    docker start transfermarkt-api")
    print("    python fetch_transfermarkt_values.py")


if __name__ == "__main__":
    main()