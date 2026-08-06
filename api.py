"""
api.py
========
TransferRumor REST API (FastAPI).

Mevcut is mantigini (data_loader / player_segmentation / recommendation_engine)
HTTP uzerinden sunar. Streamlit'ten bagimsizdir - herhangi bir frontend
(Next.js, React, mobil uygulama) bu API'yi tuketebilir.

CALISTIRMA:
    pip install fastapi uvicorn
    uvicorn api:app --reload --port 8100

DOKUMANTASYON (otomatik uretilir):
    http://localhost:8100/docs        - Swagger UI
    http://localhost:8100/redoc       - ReDoc

NOT: transfermarkt-api Docker container'i 8000 portunu kullaniyor,
     bu yuzden API 8100'de calisiyor.
"""

import os
from functools import lru_cache
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from data_loader import get_available_seasons, load_players
from player_segmentation import segment_players
from recommendation_engine import (
    analyze_squad,
    compute_league_strength,
    get_team_context,
    recommend_transfers,
)

app = FastAPI(
    title="TransferRumor API",
    description=(
        "Futbol oyuncu segmentasyonu ve transfer oneri sistemi.\n\n"
        "**Veri kaynaklari:** istatistikler API-Football (2024 sezonu), "
        "piyasa degerleri Transfermarkt.\n\n"
        "**Onemli:** Alabilme skorlari egitilmis bir model tahmini degil, "
        "kurallara dayali karsilastirma gostergeleridir."
    ),
    version="2.0.0",
)

# Frontend farkli bir domainde calisiyor, bu yuzden CORS gerekli.
# Uretimde ALLOWED_ORIGINS ortam degiskeniyle kendi frontend adresine
# kisitla (virgulle ayrilmis liste). Ayarlanmazsa gelistirme icin acik.
_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS = (
    [o.strip() for o in _origins_env.split(",") if o.strip()]
    if _origins_env
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# VERI YUKLEME (bir kez yuklenip cache'lenir)
# --------------------------------------------------------------------------

@lru_cache(maxsize=4)
def get_dataframe(season: int) -> pd.DataFrame:
    """Sezon verisini yukleyip segmentasyonla birlestirir. Cache'lenir."""
    df = load_players(season).drop_duplicates(subset=["PLAYER", "CLUB"])
    if df.empty:
        return df
    seg = segment_players(season)
    if not seg.empty:
        df = df.merge(seg, on=["PLAYER", "CLUB"], how="left")
    perf_col = f"PERFORMANCE_SCORE_{season}"
    df["PERF_SCORE"] = (
        pd.to_numeric(df[perf_col], errors="coerce").fillna(0)
        if perf_col in df.columns else 0
    )
    return df


def _latest_season() -> int:
    seasons = get_available_seasons()
    if not seasons:
        raise HTTPException(503, "Veritabaninda veri bulunamadi.")
    return seasons[0]


def _df_or_404(season: Optional[int]) -> tuple:
    season = season or _latest_season()
    df = get_dataframe(season)
    if df.empty:
        raise HTTPException(404, f"Sezon {season} icin veri bulunamadi.")
    return df, season


def _clean(records):
    """NaN -> None (JSON'da NaN gecersizdir)."""
    return [
        {k: (None if pd.isna(v) else v) for k, v in rec.items()}
        for rec in records
    ]


# --------------------------------------------------------------------------
# PYDANTIC MODELLERI
# --------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    seasons: List[int]
    player_count: int


class Player(BaseModel):
    PLAYER: str
    CLUB: Optional[str] = None
    LEAGUE: Optional[str] = None
    NATION: Optional[str] = None
    AGE: Optional[float] = None
    POSITION: Optional[str] = None
    VALUE: Optional[float] = None
    APPEARANCES: Optional[float] = None
    MINUTES: Optional[float] = None
    GOALS: Optional[float] = None
    ASSISTS: Optional[float] = None
    RATING: Optional[float] = None


class SquadNeed(BaseModel):
    POSITION: str
    SQUAD_COUNT: int
    AVG_PERFORMANCE: float
    LEAGUE_AVG_PERFORMANCE: float
    AVG_AGE: Optional[float] = None
    AGING_RATIO: float
    NEED_SCORE: float


class TeamContext(BaseModel):
    team: str
    league: Optional[str] = None
    league_strength: float
    squad_size: int
    squad_total_value: Optional[float] = None
    squad_median_value: Optional[float] = None
    squad_max_value: Optional[float] = None
    avg_age: float


class Recommendation(BaseModel):
    PLAYER: str
    CLUB: Optional[str] = None
    LEAGUE: Optional[str] = None
    AGE: Optional[float] = None
    VALUE: Optional[float] = None
    quality: Optional[float] = Field(None, description="Lig gucune gore duzeltilmis performans")
    accessibility: Optional[float] = Field(None, description="0-100 ulasilabilirlik skoru")
    overall: Optional[float] = Field(None, description="Nihai siralama skoru")
    notes: Optional[str] = None
    affordability: Optional[float] = None
    league_pull: Optional[float] = None
    playing_time: Optional[float] = None
    age_factor: Optional[float] = None


class RecommendationResponse(BaseModel):
    team: str
    season: int
    target_position: str
    current_level: float
    context: TeamContext
    squad_needs: List[SquadNeed]
    recommendations: List[Recommendation]
    disclaimer: str


DISCLAIMER = (
    "Alabilme skorlari EGITILMIS BIR MODEL TAHMINI DEGILDIR. Gercek kulup "
    "butcesi verisi yoktur; butce hesaplari kadro piyasa degerinden turetilmis "
    "proxy'dir. Sozlesme suresi, oyuncunun ayrilma istegi ve kulubun satma "
    "niyeti gibi transferi belirleyen faktorler veride bulunmamaktadir."
)


# --------------------------------------------------------------------------
# ENDPOINT'LER
# --------------------------------------------------------------------------

@app.get("/", tags=["meta"])
def root():
    """API kok adresi - dokumantasyona yonlendirir."""
    return {
        "name": "TransferRumor API",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": [
            "/health", "/seasons", "/leagues", "/teams", "/players",
            "/teams/{team}/squad", "/teams/{team}/needs",
            "/teams/{team}/recommendations", "/stats/segments",
        ],
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health():
    """API ve veritabani durumu."""
    seasons = get_available_seasons()
    count = len(get_dataframe(seasons[0])) if seasons else 0
    return {"status": "ok", "seasons": seasons, "player_count": count}


@app.get("/seasons", tags=["meta"])
def seasons():
    """Veritabaninda bulunan sezonlar."""
    return {"seasons": get_available_seasons()}


@app.get("/leagues", tags=["meta"])
def leagues(season: Optional[int] = None):
    """Ligler ve her ligdeki takim/oyuncu sayilari."""
    df, season = _df_or_404(season)
    strength = compute_league_strength(df)
    rows = (
        df.groupby("LEAGUE")
        .agg(teams=("CLUB", "nunique"), players=("PLAYER", "count"),
             median_value=("VALUE", "median"))
        .reset_index()
    )
    rows["strength"] = rows["LEAGUE"].map(strength).round(3)
    return {"season": season, "leagues": _clean(rows.to_dict("records"))}


@app.get("/teams", tags=["meta"])
def teams(season: Optional[int] = None, league: Optional[str] = None):
    """Takim listesi (opsiyonel lige gore filtreli)."""
    df, season = _df_or_404(season)
    if league:
        df = df[df["LEAGUE"] == league]
        if df.empty:
            raise HTTPException(404, f"'{league}' ligi bulunamadi.")
    rows = (
        df.groupby(["CLUB", "LEAGUE"])
        .agg(squad_size=("PLAYER", "count"), avg_age=("AGE", "mean"),
             total_value=("VALUE", "sum"))
        .reset_index()
        .sort_values("CLUB")
    )
    rows["avg_age"] = rows["avg_age"].round(1)
    return {"season": season, "teams": _clean(rows.to_dict("records"))}


@app.get("/players", response_model=List[Player], tags=["players"])
def players(
    season: Optional[int] = None,
    league: Optional[str] = None,
    team: Optional[str] = None,
    position: Optional[str] = Query(None, pattern="^(ATTACK|MIDFIELD|DEFENDER)$"),
    min_age: int = 15,
    max_age: int = 45,
    search: Optional[str] = Query(None, description="Isimde gecen metin"),
    limit: int = Query(50, le=500),
    offset: int = 0,
):
    """Oyuncu arama ve filtreleme."""
    df, _ = _df_or_404(season)
    if league:
        df = df[df["LEAGUE"] == league]
    if team:
        df = df[df["CLUB"] == team.upper()]
    if position:
        df = df[df["POSITION"] == position]
    if search:
        df = df[df["PLAYER"].str.contains(search, case=False, na=False)]
    df = df[(df["AGE"] >= min_age) & (df["AGE"] <= max_age)]

    cols = ["PLAYER", "CLUB", "LEAGUE", "NATION", "AGE", "POSITION", "VALUE",
            "APPEARANCES", "MINUTES", "GOALS", "ASSISTS", "RATING"]
    out = df[cols].iloc[offset: offset + limit]
    return _clean(out.to_dict("records"))


@app.get("/teams/{team}/squad", tags=["teams"])
def team_squad(team: str, season: Optional[int] = None):
    """
    Bir takimin tam kadrosu: her oyuncunun segmenti, performans skoru,
    satis beklentisi ve o segment icin aksiyon onerisi.
    """
    df, season = _df_or_404(season)
    squad = df[df["CLUB"] == team.upper()]
    if squad.empty:
        raise HTTPException(404, f"'{team}' takimi bulunamadi.")

    seg_col = f"SEGMENT_{season}"
    perf_col = f"PERFORMANCE_SCORE_{season}"
    sales_col = f"SALES_EXPECTATION_PRICE_{season}"
    action_col = f"RECOMMEND_FOR_ACTION_{season}"

    cols = ["PLAYER", "POSITION", "AGE", "VALUE", "APPEARANCES",
            "MINUTES", "GOALS", "ASSISTS", "RATING"]
    rename = {}
    for src, dst in [(seg_col, "segment"), (perf_col, "performance_score"),
                     (sales_col, "sales_expectation"), (action_col, "action")]:
        if src in squad.columns:
            cols.append(src)
            rename[src] = dst

    out = squad[cols].rename(columns=rename)
    # Pozisyona sonra performansa gore sirala - en zayif oyuncular
    # kendi pozisyon grubunun sonunda gorunsun
    if "performance_score" in out.columns:
        out["_sort"] = pd.to_numeric(out["performance_score"], errors="coerce").fillna(0)
        out = out.sort_values(["POSITION", "_sort"], ascending=[True, False]).drop(columns="_sort")

    return {
        "team": team.upper(),
        "season": season,
        "squad_size": len(out),
        "squad": _clean(out.to_dict("records")),
    }


@app.get("/teams/{team}/needs", response_model=List[SquadNeed], tags=["teams"])
def team_needs(team: str, season: Optional[int] = None):
    """Pozisyon bazli kadro ihtiyac analizi."""
    df, _ = _df_or_404(season)
    analysis = analyze_squad(df, team.upper())
    if analysis.empty:
        raise HTTPException(404, f"'{team}' takimi bulunamadi.")
    return _clean(analysis.to_dict("records"))


@app.get("/teams/{team}/recommendations", response_model=RecommendationResponse, tags=["recommendations"])
def team_recommendations(
    team: str,
    season: Optional[int] = None,
    position: Optional[str] = Query(None, pattern="^(ATTACK|MIDFIELD|DEFENDER)$"),
    max_age: int = Query(35, ge=16, le=45),
    max_value: Optional[float] = Query(None, description="EUR cinsinden ust sinir"),
    leagues: Optional[List[str]] = Query(None, description="Aranacak ligler"),
    top_n: int = Query(20, le=100),
):
    """
    Kadro analizine dayali transfer onerileri.

    Pozisyon belirtilmezse en cok ihtiyac duyulan pozisyon otomatik secilir.
    """
    df, season = _df_or_404(season)
    res = recommend_transfers(
        df, team=team.upper(), position=position, max_age=max_age,
        max_value=max_value, source_leagues=leagues, top_n=top_n,
    )
    if "error" in res:
        raise HTTPException(404, res["error"])

    recs = res["recommendations"]
    rec_list = []
    if not recs.empty:
        mapped = recs.rename(columns={
            "LEAGUE_ADJ_PERF": "quality",
            "SIGNING_SCORE": "accessibility",
            "FINAL_RANK_SCORE": "overall",
            "WHY": "notes",
            "_AFFORDABILITY": "affordability",
            "_LEAGUE_PULL": "league_pull",
            "_PLAYING_TIME": "playing_time",
            "_AGE_FACTOR": "age_factor",
        })
        keep = ["PLAYER", "CLUB", "LEAGUE", "AGE", "VALUE", "quality",
                "accessibility", "overall", "notes", "affordability",
                "league_pull", "playing_time", "age_factor"]
        rec_list = _clean(mapped[[c for c in keep if c in mapped.columns]].to_dict("records"))

    return {
        "team": team.upper(),
        "season": season,
        "target_position": res["target_position"],
        "current_level": res["current_level"],
        "context": res["context"],
        "squad_needs": _clean(res["squad_analysis"].to_dict("records")),
        "recommendations": rec_list,
        "disclaimer": DISCLAIMER,
    }


@app.get("/stats/segments", tags=["stats"])
def segment_distribution(season: Optional[int] = None, position: Optional[str] = None):
    """Segment dagilimi (grafikler icin)."""
    df, season = _df_or_404(season)
    seg_col = f"SEGMENT_{season}"
    if seg_col not in df.columns:
        raise HTTPException(404, "Segment verisi bulunamadi.")
    if position:
        df = df[df["POSITION"] == position]
    counts = df[seg_col].value_counts().reset_index()
    counts.columns = ["segment", "count"]
    return {"season": season, "position": position,
            "distribution": _clean(counts.to_dict("records"))}