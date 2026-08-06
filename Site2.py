import streamlit as st
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from player_segmentation import segment_players
from data_loader import load_players, get_available_seasons
from recommendation_engine import recommend_transfers
import joblib

# HIBRIT MIMARI: api_football_data.db
#   - istatistikler  -> API-Football (fetch_api_football_data.py)
#   - piyasa degeri  -> Transfermarkt (fetch_transfermarkt_values.py)
#
# NOT: yellowbrick'in KElbowVisualizer'i guncel scikit-learn surumleriyle
# uyumsuz hale geldi (estimator tip kontrolu hata veriyor: "not a clustering
# estimator"). Bu yuzden yellowbrick bagimliligi tamamen kaldirildi; elbow
# (dirsek) noktasi asagida birkac satirlik sade bir fonksiyonla (Kneedle
# yontemi - ilk/son noktayi birlestiren dogruya en uzak nokta) hesaplaniyor.


def _find_elbow_k(k_values, inertias):
    """Basit 'kneedle' yontemi: ilk-son noktayi birlestiren dogruya en uzak k."""
    if len(k_values) <= 2:
        return k_values[0]
    x1, y1 = k_values[0], inertias[0]
    x2, y2 = k_values[-1], inertias[-1]
    denom = ((y2 - y1) ** 2 + (x2 - x1) ** 2) ** 0.5
    if denom == 0:
        return k_values[0]
    distances = [
        abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / denom
        for x, y in zip(k_values, inertias)
    ]
    return k_values[int(np.argmax(distances))]


def _non_feature_columns(seasons):
    """KMeans'e sokulmayacak kimlik + segmentasyon metin sutunlari (sezona gore degisir)."""
    cols = ["PLAYER", "CLUB", "NATION", "VALUE", "POSITION", "LEAGUE", "PERF_SCORE"]
    for s in seasons:
        cols += [
            f"SEGMENT_{s}",
            f"SALES_EXPECTATION_PRICE_{s}",
            f"RECOMMEND_FOR_ACTION_{s}",
        ]
    return cols


@st.cache_data
def load_data():
    """
    SQLite'taki (api_football_data.db) en guncel sezonu ana veri, DB'de
    bulunan TUM sezonlari da segmentasyon icin kullanarak birlestirilmis
    DataFrame'i olusturur.
    """
    seasons = get_available_seasons()
    if not seasons:
        st.error(
            "SQLite veritabaninda (api_football_data.db) hic veri bulunamadi. "
            "Once fetch_api_football_data.py scriptini calistirip veri cek."
        )
        st.stop()

    latest_season = seasons[0]
    df_main = load_players(latest_season)
    if df_main.empty:
        st.error(f"En guncel sezon ({latest_season}) icin oyuncu verisi bulunamadi.")
        st.stop()
    df_main = df_main.drop_duplicates(subset=["PLAYER", "CLUB"])

    df = df_main
    for season in seasons:
        df_season = segment_players(season)
        if df_season.empty:
            continue
        df = pd.merge(df, df_season, on=["PLAYER", "CLUB"], how="left")

    # Oneri motoru sayisal bir performans skoru bekliyor; en guncel
    # sezonun segmentasyon skorunu PERF_SCORE olarak disari aciyoruz.
    latest_perf_col = f"PERFORMANCE_SCORE_{latest_season}"
    if latest_perf_col in df.columns:
        df["PERF_SCORE"] = pd.to_numeric(df[latest_perf_col], errors="coerce").fillna(0)
    else:
        df["PERF_SCORE"] = 0

    return df, seasons


ALL_LEAGUES_LABEL = "All Leagues"


def _league_filtered_teams(dataframe, key_suffix):
    """
    Sidebar'a lig secici ekler ve secilen lige gore takim listesini daraltir.
    Donen deger: (secilen_lig, o_ligdeki_takimlar_listesi)
    12 lig x ~20 takim = 233 takim tek listede zor kullanildigi icin
    once lig secilip takim listesi daraltiliyor.
    """
    leagues = sorted(dataframe["LEAGUE"].dropna().unique())
    lig = st.sidebar.selectbox("League:", leagues, key=f"lig_{key_suffix}")
    teams = sorted(dataframe.loc[dataframe["LEAGUE"] == lig, "CLUB"].dropna().unique())
    return lig, teams


def get_kmeans_model(position, dataframe, non_feature_columns):
    model_path = f"kmeans_{position.lower()}.joblib"

    data = dataframe[dataframe["POSITION"] == position]
    X = data.drop(non_feature_columns, axis=1, errors="ignore").values
    n_features = X.shape[1]

    # Cache'lenmis model varsa kullan - AMA ozellik sayisi uyusuyorsa.
    # Veri setine yeni sutun eklendiginde (orn. zengin istatistikler) eski
    # model gecersiz kalir; bu durumda sessizce yeniden egitiyoruz.
    try:
        kmeans = joblib.load(model_path)
        if getattr(kmeans, "n_features_in_", None) == n_features:
            return kmeans
    except (FileNotFoundError, EOFError, KeyError):
        pass

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    max_k = min(20, len(X_scaled) - 1)
    if max_k < 3:
        best_k = max(2, min(max_k, 2))
    else:
        k_values = list(range(2, max_k + 1))
        inertias = []
        for k in k_values:
            km = KMeans(n_clusters=k, random_state=17, n_init=10).fit(X_scaled)
            inertias.append(km.inertia_)
        best_k = _find_elbow_k(k_values, inertias)

    kmeans = KMeans(n_clusters=best_k, random_state=17, n_init=10).fit(X_scaled)
    joblib.dump(kmeans, model_path)
    return kmeans


def ilgilenilebilecek_oyuncular(dataframe, non_feature_columns):
    st.header("Transfer Player Prediction")

    lig, teams = _league_filtered_teams(dataframe, "transfer")
    takim = st.sidebar.selectbox("Team:", teams, key="takim_transfer")
    pozisyon = st.sidebar.selectbox("Position:", sorted(dataframe["POSITION"].unique()))

    # Aday oyuncularin hangi lig(ler)den geleceği - kendi liginden veya
    # tum liglerden arama yapilabilsin.
    all_leagues = sorted(dataframe["LEAGUE"].dropna().unique())
    hedef_lig = st.sidebar.selectbox(
        "Search players in:", [ALL_LEAGUES_LABEL] + all_leagues, key="hedef_lig"
    )

    yas = st.sidebar.slider("Age Range:", min_value=16, max_value=40, key="yas_slider")

    value_available = dataframe["VALUE"].notna().any()
    if value_available:
        deger = st.sidebar.slider("Value Range:", min_value=0, max_value=150000000, step=100000, key="deger_slider")
    else:
        st.sidebar.info(
            "Piyasa degeri (Value) bilgisi bulunamadi, bu filtre devre disi."
        )
        deger = None

    if st.sidebar.button("Get Predictions🔍"):
        kmeans = get_kmeans_model(pozisyon, dataframe, non_feature_columns)

        position_df = dataframe[dataframe["POSITION"] == pozisyon].copy()

        X = position_df.drop(non_feature_columns, axis=1, errors="ignore").values

        position_df["CLUSTER"] = kmeans.predict(StandardScaler().fit_transform(X))
        position_df["CLUSTER"] = position_df["CLUSTER"] + 1

        team_clusters = position_df.loc[position_df["CLUB"] == takim, "CLUSTER"]
        if team_clusters.empty:
            st.warning(
                f"{takim} takiminda '{pozisyon}' pozisyonunda oyuncu bulunamadi. "
                f"Baska bir pozisyon deneyin."
            )
            return

        target_cluster = round(team_clusters.mean())
        mask = (
            (position_df["POSITION"] == pozisyon)
            & (position_df["AGE"] <= yas)
            & (position_df["CLUB"] != takim)
            & (position_df["CLUSTER"] == target_cluster)
        )
        if hedef_lig != ALL_LEAGUES_LABEL:
            mask &= position_df["LEAGUE"] == hedef_lig
        if value_available:
            mask &= position_df["VALUE"] <= deger

        transfer_edilebilecekler = position_df.loc[mask]

        if transfer_edilebilecekler.empty:
            st.info("Bu kriterlere uyan oyuncu bulunamadi. Filtreleri genisletmeyi deneyin.")
        else:
            st.write(f"{len(transfer_edilebilecekler)} oyuncu bulundu:")
            st.write(
                transfer_edilebilecekler[
                    ["PLAYER", "CLUB", "LEAGUE", "POSITION", "AGE", "VALUE"]
                ]
            )


def oyuncu_kazanc_beklentisi(dataframe, seasons):
    st.header("Sales Expectation and Performance Analysis")
    lig, teams = _league_filtered_teams(dataframe, "sales")
    takim2 = st.sidebar.selectbox("Team: ", teams, key="takim_sales")
    season = st.sidebar.selectbox("Season:", [str(s) for s in seasons], key="season_sales")

    if st.sidebar.button("Get Predictions🔍"):
        segment_col = f"SEGMENT_{season}"
        performance_score_col = f"PERFORMANCE_SCORE_{season}"
        sales_exp_col = f"SALES_EXPECTATION_PRICE_{season}"

        oyuncu_sonuc = dataframe[dataframe["CLUB"] == takim2][
            ["PLAYER", "VALUE", sales_exp_col, segment_col, performance_score_col]
        ]
        if oyuncu_sonuc.empty:
            st.info(f"{takim2} icin veri bulunamadi.")
        else:
            st.write(oyuncu_sonuc)


def oyunculara_göre_aksiyon_tavsiyesi(dataframe, seasons):
    st.header("Recommendation for Action")
    lig, teams = _league_filtered_teams(dataframe, "action")
    takim2 = st.sidebar.selectbox("Team: ", teams, key="takim_action")
    season = st.sidebar.selectbox("Season:", [str(s) for s in seasons], key="season_action")

    if st.sidebar.button("Get Recommendations🔍"):
        recommendation_col = f"RECOMMEND_FOR_ACTION_{season}"
        takim_df = dataframe.loc[
            (dataframe["CLUB"] == takim2),
            ["PLAYER", "CLUB", "AGE", "POSITION", recommendation_col],
        ]
        if takim_df.empty:
            st.info(f"{takim2} icin veri bulunamadi.")
        else:
            st.write(takim_df)


def kadro_bazli_oneri(dataframe):
    st.header("Squad-Based Transfer Advisor")
    st.caption(
        "Takimin kadro yapisini analiz eder, en cok takviye gereken pozisyonu "
        "belirler ve butce/lig/forma suresi faktorlerini birlikte degerlendirerek "
        "ulasilabilir hedefler onerir."
    )

    lig, teams = _league_filtered_teams(dataframe, "advisor")
    takim = st.sidebar.selectbox("Team:", teams, key="takim_advisor")

    pos_choice = st.sidebar.selectbox(
        "Position:", ["Auto (most needed)", "ATTACK", "MIDFIELD", "DEFENDER"], key="pos_advisor"
    )
    position = None if pos_choice.startswith("Auto") else pos_choice

    max_age = st.sidebar.slider("Max age:", 16, 40, 32, key="age_advisor")

    all_leagues = sorted(dataframe["LEAGUE"].dropna().unique())
    src = st.sidebar.multiselect(
        "Search in leagues (empty = all):", all_leagues, key="src_advisor"
    )

    budget_m = st.sidebar.slider(
        "Max value (million EUR):", 0, 200, 30, key="budget_advisor"
    )

    if not st.sidebar.button("Analyze & Recommend🔍"):
        return

    res = recommend_transfers(
        dataframe,
        team=takim,
        position=position,
        max_age=max_age,
        max_value=budget_m * 1_000_000,
        source_leagues=src or None,
        top_n=20,
    )

    if "error" in res:
        st.error(res["error"])
        return

    ctx = res["context"]
    st.subheader(f"{takim} — Squad Profile")
    col1, col2, col3 = st.columns(3)
    col1.metric("Squad size", ctx["squad_size"])
    col2.metric("Average age", f"{ctx['avg_age']:.1f}")
    col3.metric("Squad value", f"€{ctx['squad_total_value']/1_000_000:,.0f}M"
                if pd.notna(ctx["squad_total_value"]) else "n/a")

    st.subheader("Squad Needs by Position")
    st.caption("NEED_SCORE: performans acigi (%50) + kadro derinligi (%30) + yaslanma (%20)")
    st.dataframe(res["squad_analysis"], use_container_width=True)

    st.subheader(f"Recommended Targets — {res['target_position']}")
    st.caption(
        f"Takimin bu pozisyondaki mevcut seviyesi (lig-duzeltilmis): "
        f"{res['current_level']}. Yalnizca bunun uzerindeki oyuncular listeleniyor."
    )

    recs = res["recommendations"]
    if recs.empty:
        st.info("Bu kriterlere uyan oyuncu bulunamadi. Butce veya yas sinirini genisletmeyi deneyin.")
        return

    display = recs[[
        "PLAYER", "CLUB", "LEAGUE", "AGE", "VALUE",
        "LEAGUE_ADJ_PERF", "SIGNING_SCORE", "FINAL_RANK_SCORE", "WHY",
    ]].rename(columns={
        "LEAGUE_ADJ_PERF": "QUALITY",
        "SIGNING_SCORE": "ACCESSIBILITY",
        "FINAL_RANK_SCORE": "OVERALL",
        "WHY": "NOTES",
    })
    st.dataframe(display, use_container_width=True)

    with st.expander("How are these scores calculated? (important caveats)"):
        st.markdown(
            """
**QUALITY** — Oyuncunun pozisyonundaki performans skoru, ligin gucune gore
duzeltilmis. (Allsvenskan'da 5 almak ile Premier Lig'de 5 almak ayni degil.)

**ACCESSIBILITY** — Kurallara dayali bir ulasilabilirlik skoru:
- Butce uygunlugu (%40) — oyuncunun degeri, kulubun en pahali oyuncusuna kiyasla
- Lig cazibesi (%25) — hedef lig, oyuncunun mevcut liginden gucluyse lehte
- Forma suresi (%20) — kulubunde az oynayan oyuncu ayrilmaya daha acik
- Yas (%15) — 24-30 arasi en ulasilabilir kabul ediliyor

---
**⚠️ Bu skorlar bir tahmin modeli DEGILDIR.**

- Gercek kulup butcesi verisi elimizde yok; "butce uygunlugu" kadro piyasa
  degerinden turetilmis bir **proxy**.
- ACCESSIBILITY gercek transfer sonuclariyla egitilmis/dogrulanmis bir olasilik
  degil, kurallara dayali bir **karsilastirma gostergesi**. "%80" bir oyuncunun
  %80 ihtimalle alinacagi anlamina GELMEZ; sadece listedeki digerlerine gore
  daha ulasilabilir oldugunu gosterir.
- Sozlesme suresi, oyuncunun ayrilma istegi, kulubun satma niyeti, serbest kalma
  bedeli gibi transferi asil belirleyen faktorler veride yok.
- Istatistikler 2024 sezonuna ait; piyasa degerleri guncel. Bu zaman farki
  bazi oyuncularda tutarsizlik yaratabilir.
            """
        )


def main():
    new_title = '<p style="font-family:algerian; color:White; font-size: 55px;">TRANSFER RUMOR⚽️</p>'
    st.markdown(new_title, unsafe_allow_html=True)

    df, seasons = load_data()
    non_feature_columns = _non_feature_columns(seasons)

    selected_option = st.sidebar.radio(
        "Choose Your Action:",
        (
            "Squad-Based Transfer Advisor",
            "Transfer Player Prediction",
            "Sales Expectation and Performance Analysis",
            "Recommendation for Action",
        ),
    )

    if selected_option == "Squad-Based Transfer Advisor":
        kadro_bazli_oneri(df)
    elif selected_option == "Transfer Player Prediction":
        ilgilenilebilecek_oyuncular(df, non_feature_columns)
    elif selected_option == "Sales Expectation and Performance Analysis":
        oyuncu_kazanc_beklentisi(df, seasons)
    else:
        oyunculara_göre_aksiyon_tavsiyesi(df, seasons)


if __name__ == "__main__":
    main()

page_bg_img = f"""
<style>
[data-testid="stAppViewContainer"] > .main {{
background-image: url("https://images.hdqwalls.com/wallpapers/football-ground-sun-rays-4k-ev.jpg");
background-size: 110%;
background-position: top left;
background-repeat: no-repeat;
background-attachment: local;
}}

[data-testid="stHeader"] {{
background: rgba(0,0,0,0);
}}

[data-testid="stToolbar"] {{
right: 2rem;
}}
</style>
"""

st.markdown(page_bg_img, unsafe_allow_html=True)