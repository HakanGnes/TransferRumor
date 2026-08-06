"""
retry_not_found.py
====================
market_values tablosunda 'not_found' (veya 'error'/'timeout') olarak
isaretlenmis kayitlari SILER, basarili 'name_only' sonuclara DOKUNMAZ.
Bu sayede fetch_transfermarkt_values.py tekrar calistirildiginda sadece
daha once bulunamayan oyuncular icin (artik tam isimle) yeniden denenir.

KULLANIM:
    python retry_not_found.py
"""

import sqlite3

conn = sqlite3.connect("api_football_data.db")

before = conn.execute("SELECT match_confidence, COUNT(*) FROM market_values GROUP BY match_confidence").fetchall()
print("Silme oncesi durum:")
for confidence, count in before:
    print(f"  {confidence}: {count}")

deleted = conn.execute(
    "DELETE FROM market_values WHERE match_confidence IN ('not_found', 'error', 'timeout')"
).rowcount
conn.commit()

print(f"\n{deleted} kayit silindi (sadece basarisiz olanlar).")
print("Basarili 'name_only' kayitlar korundu. Simdi fetch_transfermarkt_values.py'yi tekrar calistirabilirsin.")