# TransferRumor ⚽️

**[→ Canlı demo](https://SENIN-VERCEL-ADRESIN.vercel.app)** · [API dokümantasyonu](https://SENIN-RENDER-ADRESIN.onrender.com/docs)

> API ücretsiz katmanda barındırılıyor ve 15 dakika kullanılmayınca uykuya
> geçiyor. İlk açılış 30-60 saniye sürebilir, sonrası anında yanıtlar.

Kadro analizine dayalı futbol transfer öneri sistemi. Bir takımın hangi
pozisyonunun takviye istediğini tespit eder, o pozisyon için bütçeye ve
ulaşılabilirliğe göre sıralanmış hedefler önerir.

**Kapsam:** 12 lig · 233 takım · 11.645 oyuncu · 7.266 oyuncu için piyasa değeri

---

## Ne yapar

**Kadro ihtiyaç analizi** — Her pozisyon için bir ihtiyaç puanı hesaplar:
performans açığı (lig ortalamasına göre, %50), kadro derinliği (%30) ve
yaşlanma oranı (%20). Arayüzde bu, saha diyagramı üzerinde ısı haritası
olarak gösterilir.

**Oyuncu segmentasyonu** — Her oyuncu, pozisyonuna uygun metriklerle
yüzdelik dilime göre puanlanır ve yaş kategorisiyle birleştirilerek bir
segmente atanır (`Young_Flawless`, `Mature_Under_expected` gibi 20 segment).
Metrikler pozisyona göre değişir:

| Pozisyon | Ana metrikler |
|---|---|
| Hücum | gol/90, şut isabeti, asist/90, kilit pas, dripling başarısı |
| Orta saha | kilit pas/90, pas hacmi, asist, müdahale, top kapma |
| Defans | müdahale/90, top kapma/90, blok, ikili mücadele kazanma oranı |

Kalite metrikleri **90 dakika başına** normalize edilir; ham toplamlar
"çok oynayan" ile "iyi oynayan"ı karıştırır.

**Transfer önerisi** — Adaylar, takımın o pozisyondaki mevcut seviyesinin
üzerinde olmak zorunda. Sıralama iki bileşenden oluşur:

- *Kalite* — performans skoru, **lig gücüne göre düzeltilmiş**
  (Allsvenskan'da 5 almak ile Premier Lig'de 5 almak aynı değil)
- *Ulaşılabilirlik* — bütçe uygunluğu (%40), lig cazibesi (%25),
  forma süresi (%20), yaş (%15)

**Kadro değerlendirmesi** — Takımın kendi oyuncuları için segment bazlı
aksiyon önerileri ("elindekilerle ne yap").

---

## Bilinen sınırlar

Bu bölüm bilerek öne konuldu; skorların ne olmadığını bilmek onları doğru
okumak için gerekli.

- **Ulaşılabilirlik skoru bir tahmin modeli değildir.** Gerçek transfer
  sonuçlarıyla eğitilmemiş, doğrulanmamış; kurallara dayalı bir
  karşılaştırma göstergesidir. "80" bir oyuncunun %80 ihtimalle alınacağı
  anlamına gelmez, yalnızca listedeki diğerlerine göre daha ulaşılabilir
  olduğunu gösterir.
- **Gerçek kulüp bütçesi verisi yok.** Bütçe hesapları kadro piyasa
  değerinden türetilmiş proxy'dir.
- **Sözleşme süresi, oyuncunun ayrılma isteği, kulübün satma niyeti ve
  serbest kalma bedeli veride yok.** Transferi asıl belirleyen faktörler
  bunlar olabilir.
- **İstatistikler 2024 sezonuna ait, piyasa değerleri güncel.** Bu zaman
  farkı bazı oyuncularda tutarsızlık yaratabilir. (API-Football ücretsiz
  planı 2022-2024 sezonlarıyla sınırlı.)
- **Piyasa değerleri isim eşleştirmesiyle bulunuyor.** Aynı isimli farklı
  oyuncular nadiren yanlış eşleşebilir.
- Kaleciler kapsam dışı.

---

## Mimari

```
Veri toplama            Depolama          Servis            Arayüz
─────────────           ─────────         ──────            ──────
fetch_api_football  ┐                  ┌ api.py         ┌ frontend/  (Next.js)
  (istatistikler)   ├→ api_football  ──┤  (FastAPI)     │
fetch_transfermarkt ┘   _data.db       └ Site2.py       └ /docs      (Swagger)
  (piyasa değeri)       (SQLite)         (Streamlit)
```

İş mantığı (`data_loader`, `player_segmentation`, `recommendation_engine`)
arayüzden bağımsızdır; hem FastAPI hem Streamlit aynı modülleri kullanır.

### Dosyalar

**Uygulama çekirdeği**

| Dosya | Görev |
|---|---|
| `data_loader.py` | SQLite → DataFrame, per-90 normalizasyon, eksik veri politikası |
| `player_segmentation.py` | Pozisyon bazlı puanlama ve segment atama |
| `recommendation_engine.py` | Kadro analizi, lig gücü, ulaşılabilirlik skoru |
| `api.py` | FastAPI REST servisi |
| `Site2.py` | Streamlit arayüzü (alternatif) |
| `frontend/` | Next.js arayüzü |

**Veri toplama ve bakım**

| Dosya | Görev |
|---|---|
| `fetch_api_football_data.py` | API-Football'dan istatistik çeker |
| `fetch_transfermarkt_values.py` | Transfermarkt'tan piyasa değeri çeker |
| `migrate_rich_stats.py` | `raw_json`'dan zengin istatistikleri sütunlara çıkarır |
| `reset_market_values.py` | Piyasa değeri tablosunu sıfırlar |
| `retry_not_found.py` | Bulunamayan eşleşmeleri yeniden dener |
| `find_league_id.py` | Lig ID'si bulucu |
| `slim_db.py` | `raw_json` sütununu kaldırıp DB'yi küçültür |

---

## Kurulum

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### API'yi çalıştır

```bash
uvicorn api:app --reload --port 8100
```

- `http://localhost:8100/docs` — Swagger arayüzü
- `http://localhost:8100/health` — veri durumu

### Arayüzü çalıştır

Ayrı bir terminalde:

```bash
cd frontend
npm install
npm run dev
```

`http://localhost:3000`

Backend adresi `frontend/.env.local` içindeki `NEXT_PUBLIC_API_URL` ile
ayarlanır.

### Streamlit sürümü (alternatif)

```bash
streamlit run Site2.py
```

---

## Veriyi güncelleme

İstatistikler için API-Football hesabı (ücretsiz plan: 100 istek/gün)
gerekir:

```bash
$env:API_FOOTBALL_KEY = "anahtarin"     # PowerShell
python fetch_api_football_data.py   # kota bitince durur, ertesi gün devam eder
python migrate_rich_stats.py        # zengin istatistikleri çıkar
```

Piyasa değerleri için kendi bilgisayarında çalışan bir
[transfermarkt-api](https://github.com/felipeall/transfermarkt-api)
örneği gerekir:

```bash
docker start transfermarkt-api
python fetch_transfermarkt_values.py
```

Her iki script de kesintiye uğrarsa kaldığı yerden devam eder.

---

## API uç noktaları

| Uç nokta | Döndürdüğü |
|---|---|
| `GET /leagues` | Ligler, takım/oyuncu sayıları, lig gücü |
| `GET /teams?league=` | Takımlar, kadro büyüklüğü, toplam değer |
| `GET /players` | Oyuncu arama (lig, takım, pozisyon, yaş, isim filtresi) |
| `GET /teams/{team}/squad` | Kadro: segment, satış beklentisi, aksiyon önerisi |
| `GET /teams/{team}/needs` | Pozisyon bazlı ihtiyaç analizi |
| `GET /teams/{team}/recommendations` | Transfer önerileri, skor bileşenleriyle |
| `GET /stats/segments` | Segment dağılımı |

---

## Canlıya alma

Frontend Vercel'de, API Render'da barındırılıyor.

**API (Render)** — `New > Blueprint` ile bu repoyu bağla; `render.yaml`
servisi otomatik oluşturur. Servis ayağa kalktıktan sonra panelden
`ALLOWED_ORIGINS` değişkenine Vercel adresini yaz (CORS için gerekli).

**Frontend (Vercel)** — `New Project` ile repoyu bağla, **Root Directory**
olarak `frontend` seç. Environment Variables bölümüne ekle:

```
NEXT_PUBLIC_API_URL = https://<render-servis-adin>.onrender.com
```

Sıralama önemli: önce API'yi dağıt, adresini al, sonra Vercel'e gir.
Vercel adresini aldıktan sonra Render'daki `ALLOWED_ORIGINS`'i güncelle.

---

## Teknolojiler

Python · pandas · scikit-learn · FastAPI · SQLite ·
Next.js · TypeScript · Tailwind CSS · Framer Motion

---

## Not

Kişisel/eğitim amaçlı bir projedir, ticari kullanım için tasarlanmamıştır.
Veri kaynaklarının kullanım şartları kendi sorumluluğunuzdadır.