# TransferRumor — Frontend

Next.js 16 + Tailwind 4 + Framer Motion arayuzu.

## Calistirma

Once backend'in ayakta oldugundan emin ol (proje kokunde):

```bash
uvicorn api:app --reload --port 8100
```

Sonra bu klasorde:

```bash
npm install
npm run dev
```

http://localhost:3000

## Yapilandirma

`.env.local` icindeki `NEXT_PUBLIC_API_URL` backend adresini belirler.
Deploy ederken kendi API URL'inle degistir.

## Tasarim notlari

Palet ve tipografi "floodlit gece maci" yonunden turetildi:
derin saha lacivertisi zemin, tebesir beyazi metin, projektor amberi vurgu.
Display font (Barlow Condensed) skorboard/forma numarasi hissi verir.

Imza oge: `PitchMap` — kadro ihtiyacini tablo yerine gercek saha diyagrami
uzerinde isi haritasi olarak gosterir. "Defans zayif" zaten mekansal bir
bilgi oldugu icin mekansal gosteriliyor. Bolgeye tiklayinca o pozisyon
icin oneri getirir.
