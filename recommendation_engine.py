"""
recommendation_engine.py
==========================
Takim odakli transfer oneri motoru. Dort bilesen:

    1. KADRO ANALIZI     - takimin hangi pozisyonu zayif / yaslaniyor
    2. BUTCE KAPASITESI  - kadro piyasa degerinden turetilen PROXY gostergeler
    3. OYUNCU DEGERI     - kariyer evresi + performans + fiyat/performans
    4. ALABILME SKORU    - kurallara dayali sezgisel bir uygunluk skoru

!!! ONEMLI DURUSTLUK NOTU !!!
    - Elimizde GERCEK transfer gecmisi ve kulup butcesi verisi YOK.
      "Butce" hesaplari kadro piyasa degerinden turetilmis PROXY'dir.
    - "Alabilme skoru" EGITILMIS BIR MODEL TAHMINI DEGILDIR. Gercek transfer
      sonuclariyla dogrulanmamis, kurallara dayali bir skordur. Yuzde gibi
      gorunse de istatistiksel bir olasilik degildir; karsilastirmali bir
      gosterge olarak okunmalidir (A oyuncusu B'den daha ulasilabilir gibi).
    - Sozlesme suresi, oyuncunun ayrilma istegi, kulubun satma niyeti,
      serbest kalma bedeli gibi GERCEK transferi belirleyen faktorler
      veride yok. Skor bunlari bilmiyor.
"""

import numpy as np
import pandas as pd

# Kadro analizinde pozisyon basina beklenen minimum oyuncu sayisi
EXPECTED_SQUAD_SIZE = {"ATTACK": 6, "MIDFIELD": 7, "DEFENDER": 7}

# Yaslanma riski esigi
AGING_AGE = 30


# --------------------------------------------------------------------------
# 1. LIG GUCU (alabilme skorunda kullaniliyor)
# --------------------------------------------------------------------------

def compute_league_strength(df: pd.DataFrame) -> dict:
    """
    Her ligin gorece gucunu, o ligdeki oyuncularin medyan piyasa degerinden
    turetir ve 0-1 arasina olceklendirir. Guclu ligden zayif lige transfer
    daha zor kabul edilir.
    """
    med = df.groupby("LEAGUE")["VALUE"].median().dropna()
    if med.empty:
        return {}
    # Log olcek: piyasa degerleri ligler arasi cok genis araliga yayiliyor
    log_med = np.log1p(med)
    lo, hi = log_med.min(), log_med.max()
    if hi == lo:
        return {lg: 0.5 for lg in med.index}
    return ((log_med - lo) / (hi - lo)).to_dict()


def add_league_adjusted_performance(df: pd.DataFrame, league_strength: dict) -> pd.DataFrame:
    """
    PERF_SCORE lig ICINDE percentile ile hesaplaniyor; bu yuzden farkli
    ligler arasinda dogrudan karsilastirilamaz (Allsvenskan'da 5 olmak
    ile Premier Lig'de 5 olmak ayni sey degil).

    Lig gucuyle olceklendirip karsilastirilabilir hale getiriyoruz:
        LEAGUE_ADJ_PERF = PERF_SCORE * (0.6 + 0.4 * lig_gucu)

    Boylece guclu ligdeki bir oyuncu ayni ham skorla daha yuksek
    duzeltilmis skor alir.
    """
    out = df.copy()
    strength = out["LEAGUE"].map(league_strength).fillna(0.5)
    out["LEAGUE_ADJ_PERF"] = (out["PERF_SCORE"] * (0.6 + 0.4 * strength)).round(3)
    return out


def _playing_time_ratio(df: pd.DataFrame) -> pd.Series:
    """
    Oyuncunun kendi LIGI ve POZISYONUNDAKI "tam forma giyen oyuncu"
    referansina (90. persentil dakika) gore ne kadar oynadigini dondurur.
    Tum adaylarin maksimumuna gore olcmek yaniltici oluyordu - o yontemde
    neredeyse herkes "az oynuyor" gorunuyordu.
    """
    benchmark = df.groupby(["LEAGUE", "POSITION"])["MINUTES"].transform(
        lambda s: s.quantile(0.90)
    )
    benchmark = benchmark.replace(0, np.nan)
    ratio = (df["MINUTES"] / benchmark).clip(upper=1.0)
    return ratio.fillna(0.5)


# --------------------------------------------------------------------------
# 2. TAKIM BAGLAMI: kadro + butce proxy
# --------------------------------------------------------------------------

def get_team_context(df: pd.DataFrame, team: str, league_strength: dict) -> dict:
    """Bir takimin kadro ve (proxy) mali profilini cikarir."""
    squad = df[df["CLUB"] == team]
    if squad.empty:
        return {}

    values = squad["VALUE"].dropna()
    league = squad["LEAGUE"].mode().iloc[0] if not squad["LEAGUE"].mode().empty else None

    return {
        "team": team,
        "league": league,
        "league_strength": league_strength.get(league, 0.5),
        "squad_size": len(squad),
        "squad_total_value": float(values.sum()) if not values.empty else np.nan,
        "squad_median_value": float(values.median()) if not values.empty else np.nan,
        # En pahali oyuncu, kulubun "yapabilecegi en buyuk transfer" icin
        # kaba bir ust sinir proxy'si olarak kullaniliyor.
        "squad_max_value": float(values.max()) if not values.empty else np.nan,
        "avg_age": float(squad["AGE"].mean()),
    }


# --------------------------------------------------------------------------
# 3. KADRO ANALIZI: hangi pozisyon zayif?
# --------------------------------------------------------------------------

def analyze_squad(df: pd.DataFrame, team: str) -> pd.DataFrame:
    """
    Takimin her pozisyonu icin guc/zayiflik analizi yapar ve bir
    "ihtiyac skoru" (0-100, yuksek = daha acil takviye gerekiyor) uretir.

    Ihtiyac skoru su bilesenlerden olusur:
      - Performans acigi : pozisyondaki oyuncularin ortalama performans
                           skoru, ligin ayni pozisyondaki ortalamasinin
                           ne kadar altinda
      - Derinlik acigi   : beklenen kadro sayisina gore eksiklik
      - Yaslanma riski   : 30+ yas oranı
    """
    squad = df[df["CLUB"] == team]
    if squad.empty:
        return pd.DataFrame()

    league = squad["LEAGUE"].mode().iloc[0] if not squad["LEAGUE"].mode().empty else None
    league_df = df[df["LEAGUE"] == league] if league else df

    rows = []
    for position in ["ATTACK", "MIDFIELD", "DEFENDER"]:
        pos_squad = squad[squad["POSITION"] == position]
        pos_league = league_df[league_df["POSITION"] == position]

        n = len(pos_squad)
        expected = EXPECTED_SQUAD_SIZE[position]

        team_perf = pos_squad["PERF_SCORE"].mean() if n else 0.0
        league_perf = pos_league["PERF_SCORE"].mean() if len(pos_league) else 0.0

        # Performans acigi: lig ortalamasinin altindaysa pozitif (0-1)
        if league_perf > 0:
            perf_gap = max(0.0, (league_perf - team_perf) / league_perf)
        else:
            perf_gap = 0.0

        # Derinlik acigi (0-1)
        depth_gap = max(0.0, (expected - n) / expected)

        # Yaslanma riski (0-1)
        aging = (pos_squad["AGE"] >= AGING_AGE).mean() if n else 1.0

        need = 100 * (0.5 * perf_gap + 0.3 * depth_gap + 0.2 * aging)

        rows.append({
            "POSITION": position,
            "SQUAD_COUNT": n,
            "AVG_PERFORMANCE": round(team_perf, 2),
            "LEAGUE_AVG_PERFORMANCE": round(league_perf, 2),
            "AVG_AGE": round(pos_squad["AGE"].mean(), 1) if n else np.nan,
            "AGING_RATIO": round(aging, 2),
            "NEED_SCORE": round(need, 1),
        })

    return pd.DataFrame(rows).sort_values("NEED_SCORE", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# 4. ALABILME SKORU
# --------------------------------------------------------------------------

def compute_signing_score(players: pd.DataFrame, ctx: dict, league_strength: dict) -> pd.DataFrame:
    """
    Her aday oyuncu icin 0-100 arasi bir "alabilme uygunlugu" skoru ve
    skorun neden o oldugunu aciklayan bilesenleri hesaplar.

    Bilesenler:
      affordability : oyuncunun degeri, kulubun en pahali oyuncusuna gore
                      ne durumda (ucuzsa yuksek)
      league_pull   : hedef kulubun ligi, oyuncunun liginden gucluyse yuksek
                      (guclu lige gitmek cazip); zayifsa dusuk
      playing_time  : oyuncu mevcut kulubunde az oynuyorsa ayrilmaya daha
                      acik kabul edilir
      age_factor    : cok genc yildizlari almak zor, orta yas daha ulasilabilir
    """
    out = players.copy()
    if out.empty:
        return out

    max_val = ctx.get("squad_max_value") or np.nan
    median_val = ctx.get("squad_median_value") or np.nan
    target_strength = ctx.get("league_strength", 0.5)

    # --- affordability ---
    # Kulubun en pahali oyuncusu, yapabilecegi en buyuk transfer icin ust
    # sinir proxy'si. Oyuncu bunun altinda kaldikca skor yukselir.
    if np.isnan(max_val) or max_val <= 0:
        affordability = pd.Series(0.5, index=out.index)
    else:
        ratio = out["VALUE"] / max_val
        affordability = (1 - ratio).clip(lower=0, upper=1)
        affordability = affordability.fillna(0.5)  # degeri bilinmeyen oyuncu

    # --- league pull ---
    src_strength = out["LEAGUE"].map(league_strength).fillna(0.5)
    # Hedef lig daha gucluyse pozitif cekim; 0-1 araligina tasiniyor
    league_pull = ((target_strength - src_strength) + 1) / 2

    # --- playing time ---
    # Az oynayan oyuncu ayrilmaya daha acik kabul edilir. Referans:
    # kendi lig+pozisyonundaki "tam forma giyen oyuncu" dakikasi.
    playing_time = 1 - _playing_time_ratio(out)

    # --- age factor ---
    # 23 alti yildizlar genelde satilmaz (kulup gelecegi); 24-30 en ulasilabilir;
    # 30+ ulasilabilir ama cazibesi dusuk.
    age = out["AGE"]
    age_factor = pd.Series(0.5, index=out.index)
    age_factor[age < 21] = 0.25
    age_factor[(age >= 21) & (age < 24)] = 0.45
    age_factor[(age >= 24) & (age <= 30)] = 0.80
    age_factor[age > 30] = 0.65

    score = 100 * (
        0.40 * affordability
        + 0.25 * league_pull
        + 0.20 * playing_time
        + 0.15 * age_factor
    )

    out["SIGNING_SCORE"] = score.round(1)
    out["_AFFORDABILITY"] = (affordability * 100).round(0)
    out["_LEAGUE_PULL"] = (league_pull * 100).round(0)
    out["_PLAYING_TIME"] = (playing_time * 100).round(0)
    out["_AGE_FACTOR"] = (age_factor * 100).round(0)

    # Insan tarafindan okunabilir aciklama
    def explain(row):
        parts = []
        if row["_AFFORDABILITY"] >= 70:
            parts.append("butce acisindan rahat")
        elif row["_AFFORDABILITY"] <= 30:
            parts.append("butce acisindan zorlayici")
        if row["_LEAGUE_PULL"] >= 65:
            parts.append("lig cazibesi lehte")
        elif row["_LEAGUE_PULL"] <= 35:
            parts.append("daha guclu ligde oynuyor")
        if row["_PLAYING_TIME"] >= 60:
            parts.append("kulubunde az oynuyor")
        elif row["_PLAYING_TIME"] <= 25:
            parts.append("kulubunde vazgecilmez")
        return ", ".join(parts) if parts else "notr"

    out["WHY"] = out.apply(explain, axis=1)
    return out


# --------------------------------------------------------------------------
# 5. ANA GIRIS: oneri uret
# --------------------------------------------------------------------------

def recommend_transfers(
    df: pd.DataFrame,
    team: str,
    position: str = None,
    max_age: int = 40,
    max_value: float = None,
    source_leagues: list = None,
    top_n: int = 20,
) -> dict:
    """
    Bir takim icin transfer onerileri uretir.

    df: PERF_SCORE sutunu ICERMELI (Site2.py bunu segmentasyondan ekler)

    Donen sozluk:
        squad_analysis : pozisyon bazli ihtiyac tablosu
        context        : takimin kadro/butce proxy profili
        recommendations: onerilen oyuncular (SIGNING_SCORE ile sirali)
        target_position: kullanilan pozisyon
    """
    league_strength = compute_league_strength(df)
    df = add_league_adjusted_performance(df, league_strength)
    ctx = get_team_context(df, team, league_strength)
    if not ctx:
        return {"error": f"{team} icin kadro verisi bulunamadi."}

    squad_analysis = analyze_squad(df, team)

    # Pozisyon verilmediyse en cok ihtiyac duyulani sec
    if position is None and not squad_analysis.empty:
        position = squad_analysis.iloc[0]["POSITION"]

    # Takimin o pozisyondaki mevcut seviyesi (lig-duzeltilmis). Onerilen
    # oyuncu bunun UZERINDE olmali, yoksa takviye anlamsiz.
    squad = df[df["CLUB"] == team]
    current_level = squad.loc[squad["POSITION"] == position, "LEAGUE_ADJ_PERF"].mean()
    if pd.isna(current_level):
        current_level = 0

    candidates = df[
        (df["POSITION"] == position)
        & (df["CLUB"] != team)
        & (df["AGE"] <= max_age)
        & (df["LEAGUE_ADJ_PERF"] > current_level)
    ].copy()

    if source_leagues:
        candidates = candidates[candidates["LEAGUE"].isin(source_leagues)]
    if max_value is not None:
        candidates = candidates[candidates["VALUE"].fillna(0) <= max_value]

    if candidates.empty:
        return {
            "squad_analysis": squad_analysis,
            "context": ctx,
            "recommendations": pd.DataFrame(),
            "target_position": position,
            "current_level": current_level,
        }

    scored = compute_signing_score(candidates, ctx, league_strength)

    # Nihai siralama: alabilme skoru ve (lig-duzeltilmis) kalite birlikte
    scored["UPGRADE"] = (scored["LEAGUE_ADJ_PERF"] - current_level).round(2)
    perf_norm = scored["LEAGUE_ADJ_PERF"].rank(pct=True) * 100
    scored["FINAL_RANK_SCORE"] = (0.45 * scored["SIGNING_SCORE"] + 0.55 * perf_norm).round(1)

    scored = scored.sort_values("FINAL_RANK_SCORE", ascending=False).head(top_n)

    return {
        "squad_analysis": squad_analysis,
        "context": ctx,
        "recommendations": scored,
        "target_position": position,
        "current_level": round(current_level, 2),
    }