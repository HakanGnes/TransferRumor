"""
migrate_rich_stats.py
=======================
players.raw_json icinde ZATEN bulunan ama tabloya cikarilmamis zengin
istatistikleri (tackles, duels, passes, dribbles, shots) ayri sutunlara
cikarir. API-Football'a HIC istek atmaz - tamamen yerel veriden calisir,
kotani harcamaz.

Bu istatistikler ozellikle DEFANS oyuncularini puanlamak icin kritik:
onceden defansciları neredeyse sadece oynama suresine gore
puanlayabiliyorduk, artik tackle/interception/blocks/duels verisi var.

DOLULUK ORANLARI (sahaya cikmis saha oyuncularinda):
    duels.total %92, passes.total %93, tackles.total %85,
    tackles.interceptions %77, dribbles.attempts %83, shots.total %78
    (dribbles.past ve passes.accuracy kullanilamayacak kadar bos, atlandi)

KULLANIM:
    python migrate_rich_stats.py
"""

import json
import sqlite3

DB_PATH = "api_football_data.db"

# (sutun_adi, raw_json_yolu) - raw_json'daki statistics[0] altindaki konum
FIELDS = [
    ("tackles_total", ("tackles", "total")),
    ("tackles_blocks", ("tackles", "blocks")),
    ("tackles_interceptions", ("tackles", "interceptions")),
    ("duels_total", ("duels", "total")),
    ("duels_won", ("duels", "won")),
    ("passes_total", ("passes", "total")),
    ("passes_key", ("passes", "key")),
    ("dribbles_attempts", ("dribbles", "attempts")),
    ("dribbles_success", ("dribbles", "success")),
    ("shots_total", ("shots", "total")),
    ("shots_on", ("shots", "on")),
]


def column_exists(conn, table, column):
    return column in [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def main():
    conn = sqlite3.connect(DB_PATH)

    for col, _ in FIELDS:
        if not column_exists(conn, "players", col):
            conn.execute(f"ALTER TABLE players ADD COLUMN {col} INTEGER")
    conn.commit()
    print(f"{len(FIELDS)} sutun hazir.")

    rows = conn.execute(
        "SELECT rowid, raw_json FROM players WHERE raw_json IS NOT NULL"
    ).fetchall()
    print(f"Islenecek satir: {len(rows)}")

    set_clause = ", ".join(f"{col} = ?" for col, _ in FIELDS)
    updated = 0
    skipped = 0

    for rowid, raw in rows:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            skipped += 1
            continue

        stats_list = data.get("statistics") or []
        stats = stats_list[0] if stats_list else {}
        if not stats:
            skipped += 1
            continue

        values = []
        for _, (group, key) in FIELDS:
            group_data = stats.get(group) or {}
            values.append(group_data.get(key))

        conn.execute(f"UPDATE players SET {set_clause} WHERE rowid = ?", values + [rowid])
        updated += 1

        if updated % 2000 == 0:
            conn.commit()
            print(f"  {updated} satir islendi...")

    conn.commit()
    print(f"\nTamamlandi. Guncellenen: {updated}, atlanan: {skipped}")

    # Ozet: kac oyuncuda dolu
    print("\nDOLULUK (sahaya cikmis saha oyuncularinda):")
    base = "FROM players WHERE appearances > 0 AND position IS NOT NULL AND position != 'Goalkeeper'"
    total = conn.execute(f"SELECT COUNT(*) {base}").fetchone()[0]
    for col, _ in FIELDS:
        n = conn.execute(f"SELECT COUNT({col}) {base}").fetchone()[0]
        print(f"  {col:24s} {n:5d}/{total}  (%{n / total * 100:.0f})")


if __name__ == "__main__":
    main()