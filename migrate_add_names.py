"""
migrate_add_names.py
======================
players tablosuna firstname/lastname sutunlari ekler ve zaten indirilmis
raw_json'lardan bu bilgiyi cikarip doldurur. API-Football'a HIC istek
atmaz (kotani harcamaz) - tamamen yerel veriden calisir.

Tek seferlik calistirilir; sutunlar zaten varsa (ikinci calistirmada)
sorunsuz sekilde atlar/gunceller.

KULLANIM:
    python migrate_add_names.py
"""

import json
import sqlite3

DB_PATH = "api_football_data.db"


def column_exists(conn, table, column):
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    return column in cols


def main():
    conn = sqlite3.connect(DB_PATH)

    if not column_exists(conn, "players", "firstname"):
        conn.execute("ALTER TABLE players ADD COLUMN firstname TEXT")
    if not column_exists(conn, "players", "lastname"):
        conn.execute("ALTER TABLE players ADD COLUMN lastname TEXT")
    conn.commit()

    rows = conn.execute(
        "SELECT rowid, raw_json FROM players WHERE raw_json IS NOT NULL"
    ).fetchall()
    print(f"Islenecek satir sayisi: {len(rows)}")

    updated = 0
    skipped = 0
    for rowid, raw in rows:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            skipped += 1
            continue

        player = data.get("player", {}) if isinstance(data, dict) else {}
        firstname = player.get("firstname")
        lastname = player.get("lastname")

        if not firstname and not lastname:
            skipped += 1
            continue

        conn.execute(
            "UPDATE players SET firstname = ?, lastname = ? WHERE rowid = ?",
            (firstname, lastname, rowid),
        )
        updated += 1

        if updated % 500 == 0:
            conn.commit()
            print(f"  {updated} satir guncellendi...")

    conn.commit()
    print(f"\nTamamlandi. Guncellenen: {updated}, atlanan (veri yok): {skipped}")


if __name__ == "__main__":
    main()