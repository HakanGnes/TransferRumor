"""
player_segmentation.py
========================
api_football_data.db'deki ham istatistiklerle (bkz. data_loader.py) her
sezon icin DINAMIK oyuncu segmentasyonu hesaplar.

METODOLOJI:
    1. Her pozisyon (ATTACK/MIDFIELD/DEFENDER) icin ilgili metrikler
       percentile'a gore 1-5 arasi puanlanir. (pd.qcut yerine percentile
       kullaniliyor cunku tekrar eden degerlerde qcut hata veriyor.)
    2. Puanlar toplanip Total_Score elde edilir.
    3. Total_Score'un kendisi percentile'a gore 5 dilime bolunerek
       Performance kategorisi (Under_expected .. Flawless) belirlenir.
    4. Age_Cat (Young/Experienced/Mature/End_Of_Career) + Performance
       birlestirilip Segment string'i olusturulur (orn. "Young_Flawless").
    5. Segment string'inden SALES_EXPECTATION_PRICE ve RECOMMEND_FOR_ACTION
       sabit lookup tablolariyla turetilir.
"""

import warnings
import numpy as np
import pandas as pd

from data_loader import load_players, get_available_seasons  # noqa: F401


_SALES_EXPECTATION_MAP = {
    "Young_Under_expected": "Low",
    "Young_Open_to_development": "Low - Mid",
    "Young_Player_with_high_potential": "Mid",
    "Young_High_performance": "High",
    "Young_Flawless": "Very_High",
    "Experienced_Under_expected": "Low",
    "Experienced_Open_to_development": "Low - Mid",
    "Experienced_Player_with_high_potential": "Mid",
    "Experienced_High_performance": "Mid - High",
    "Experienced_Flawless": "Very_High",
    "Mature_Under_expected": "Very_Low",
    "Mature_Open_to_development": "Low",
    "Mature_Player_with_high_potential": "Mid",
    "Mature_High_performance": "Mid - High",
    "Mature_Flawless": "High",
    "End_Of_Career_Under_expected": "Very_Low",
    "End_Of_Career_Open_to_development": "Low",
    "End_Of_Career_Player_with_high_potential": "Low",
    "End_Of_Career_High_performance": "Mid",
    "End_Of_Career_Flawless": "Mid - High",
}

_RECOMMEND_FOR_ACTION_MAP = {
    "Young_Under_expected": "Considering the potential of these young players, encourage them to improve their performance with extra work and training. By taking a long-term approach, support their development and show patience.",
    "Young_Open_to_development": "Create special training programs to maximize the potential of these young players. Help them gain experience by regularly giving them chances in first team matches.",
    "Young_Player_with_high_potential": "Young and high-potential players can be an important part of the team in the future. Focusing on opportunities for these players to develop their skills and gain experience can greatly benefit in the long run.",
    "Young_High_performance": "Help these young talents improve their physical condition and technical skills so that they can maintain their high performance. Encourage them to show that they are ready to give leadership roles within the team.",
    "Young_Flawless": "Help these young talents maximize their physical and technical abilities so that they can maintain their excellent performance. Encourage them to evaluate media and marketing opportunities to gain more visibility.",
    "Experienced_Under_expected": "Create individual training plans for experienced players to improve their performance and increase their motivation. Based on their past accomplishments, allow them to focus more on the team leadership role.",
    "Experienced_Open_to_development": "Take a long-term approach to preparing these experienced players for the future. Encourage them to build mentoring relationships with young players and share their knowledge.",
    "Experienced_Player_with_high_potential": "Experienced and high-potential players can make an immediate contribution to the team. Thanks to the experience they have, these players can lead in tough matches and guide young players. At the same time, making a special effort to further develop the potential of these players can increase the team's chances of success",
    "Experienced_High_performance": "Support experienced players to maintain a high level of performance. Consider increasing their leadership as one of the key players on the team, giving them more responsibility within the team.",
    "Experienced_Flawless": "Support experienced players to maintain flawless performances and strengthen their leadership roles. Strategically engage them to enable them to take on more responsibility within the team.",
    "Mature_Under_expected": "Develop a special rehabilitation and training program to help mature players return to their jerseys. Set new goals to boost their motivation and rekindle their desire to improve their performance.",
    "Mature_Open_to_development": "Create individual training and training plans to enable these mature players to develop further. Consider giving leadership roles within the team and encourage them to share their experiences with younger players.",
    "Mature_Player_with_high_potential": "Create a strategic plan to maximize the high potential of these mature players. Ensure that they maintain the proper balance of training and rest so that they can maintain their performance.",
    "Mature_High_performance": "Help mature players maintain their high level of performance and encourage them to make more impact within the team by increasing their leadership. Encourage young players to share their experiences by mentoring them.",
    "Mature_Flawless": "Help mature players maintain flawless performances and encourage them to make more impact within the team by increasing their leadership. Encourage young players to share their experiences by mentoring them",
    "End_Of_Career_Under_expected": "Provide specific support and motivation for players nearing the end of their careers to rotate their jerseys. Consider mentoring roles or assistant coaching positions to allow the team to benefit from their experience.",
    "End_Of_Career_Open_to_development": "Help players nearing the end of their careers prepare their final stages for the future of the team. Support players in thinking about their own post-career plans and training.",
    "End_Of_Career_Player_with_high_potential": "Players who are nearing the end of their careers but still have high potential can be a valuable asset to teams. Thanks to their experience, these players can give advice to young talents and increase  the morale of the team with their leadership on the field. The future contributions of these players must be carefully evaluated and aligned with the team's overall strategy.",
    "End_Of_Career_High_performance": "Provide physical and psychological support to help these players maintain their performance as they approach the end of their careers. Take full advantage of their experience by increasing their leadership role within the team.",
    "End_Of_Career_Flawless": "Help players near the end of their careers maintain flawless performances and strengthen their leadership roles. Prepare players for mentoring or managerial roles to support their post-career plans.",
}

_PERFORMANCE_LABELS = {
    1: "Under_expected",
    2: "Open_to_development",
    3: "Player_with_high_potential",
    4: "High_performance",
    5: "Flawless",
}

_AGE_BINS = [15, 22, 27, 32, 45]
_AGE_LABELS = ["Young", "Experienced", "Mature", "End_Of_Career"]

# Pozisyona gore metrikler ve yon (True: yuksek daha iyi, False: dusuk daha iyi).
# Bir metrik listede birden fazla kez gecerse agirligi artar.
#
# ONEMLI: Kalite metrikleri 90 DAKIKA BASINA (_P90) kullaniliyor - yoksa
# "cok oynayan" ile "iyi oynayan" karisir. MINUTES/APPEARANCES ayrica
# "teknik direktorun guveni / sureklilik" sinyali olarak tutuluyor.
_POSITION_METRICS = {
    "ATTACK": [
        ("GOALS_P90", True), ("GOALS_P90", True),
        ("ASSISTS_P90", True),
        ("SHOTS_P90", True),
        ("SHOT_ACCURACY", True),
        ("KEY_PASSES_P90", True),
        ("DRIBBLE_SUCC_RATE", True),
        ("RATING", True), ("RATING", True),
        ("MINUTES", True),
        ("APPEARANCES", True),
        ("CARDS_P90", False),
    ],
    "MIDFIELD": [
        ("KEY_PASSES_P90", True), ("KEY_PASSES_P90", True),
        ("ASSISTS_P90", True),
        ("PASSES_P90", True),
        ("GOALS_P90", True),
        ("TACKLES_P90", True),
        ("INTERCEPTIONS_P90", True),
        ("DUEL_WIN_RATE", True),
        ("RATING", True), ("RATING", True),
        ("MINUTES", True),
        ("APPEARANCES", True),
        ("CARDS_P90", False),
    ],
    "DEFENDER": [
        # Artik gercek defansif metrikler var (raw_json'dan cikarildi):
        # tackle, interception, blok, ikili mucadele kazanma orani.
        ("TACKLES_P90", True), ("TACKLES_P90", True),
        ("INTERCEPTIONS_P90", True), ("INTERCEPTIONS_P90", True),
        ("BLOCKS_P90", True),
        ("DUEL_WIN_RATE", True), ("DUEL_WIN_RATE", True),
        ("PASSES_P90", True),
        ("RATING", True), ("RATING", True),
        ("MINUTES", True),
        ("APPEARANCES", True),
        ("CARDS_P90", False),
    ],
}


def _percentile_score(series: pd.Series, ascending: bool = True) -> pd.Series:
    """Sayisal seriyi 1-5 arasi tam sayi skora cevirir (percentile tabanli)."""
    if series.nunique(dropna=True) <= 1:
        return pd.Series(3, index=series.index)
    pct = series.rank(pct=True, ascending=ascending, method="average")
    score = np.ceil(pct * 5).clip(lower=1, upper=5)
    return score.astype(int)


def _compute_segment_for_position(df_pos: pd.DataFrame, position: str) -> pd.DataFrame:
    df_pos = df_pos.copy()
    # Kirmizi kart 2 sari degerinde; disiplin de 90 dakika basina normalize.
    cards = df_pos["YELLOW_CARDS"].fillna(0) + df_pos["RED_CARDS"].fillna(0) * 2
    nineties = (df_pos["MINUTES"] / 90).replace(0, np.nan)
    cards_p90 = (cards / nineties)

    # Hic oynamayan oyuncu "hic kart gormedi" diye disiplinde tam puan
    # aliyordu - sahaya cikmayan biri disiplinli sayilmaz. Onlari bu
    # metrikte medyana (notr) sabitliyoruz.
    if "PLAYED" in df_pos.columns:
        neutral = cards_p90.median()
        cards_p90 = cards_p90.where(df_pos["PLAYED"] == 1, neutral)
    df_pos["CARDS_P90"] = cards_p90.fillna(cards_p90.median()).fillna(0)

    total_score = pd.Series(0, index=df_pos.index)
    for metric, ascending in _POSITION_METRICS[position]:
        total_score = total_score + _percentile_score(df_pos[metric], ascending=ascending)

    df_pos["TOTAL_SCORE"] = total_score
    performance_score = _percentile_score(df_pos["TOTAL_SCORE"], ascending=True)
    df_pos["PERFORMANCE_LABEL"] = performance_score.map(_PERFORMANCE_LABELS)
    df_pos["PERFORMANCE_SCORE"] = performance_score.astype(str)

    age_cat = pd.cut(df_pos["AGE"], bins=_AGE_BINS, labels=_AGE_LABELS, include_lowest=True)
    age_cat = age_cat.astype(str).replace("nan", "Mature")

    df_pos["SEGMENT"] = age_cat.astype(str) + "_" + df_pos["PERFORMANCE_LABEL"].astype(str)
    return df_pos


def segment_players(season):
    """
    Verilen sezon (orn. 2024) icin dinamik segmentasyon hesaplar.

    Donen sutunlar: PLAYER, SEGMENT_<season>, PERFORMANCE_SCORE_<season>,
    SALES_EXPECTATION_PRICE_<season>, RECOMMEND_FOR_ACTION_<season>
    """
    df = load_players(season)
    if df.empty:
        warnings.warn(
            f"Sezon {season} icin DB'de veri bulunamadi. "
            f"Once fetch_api_football_data.py'yi calistirdigindan emin ol."
        )
        return pd.DataFrame()

    segmented_parts = []
    for position in ["ATTACK", "MIDFIELD", "DEFENDER"]:
        df_pos = df[df["POSITION"] == position]
        if df_pos.empty:
            continue
        segmented_parts.append(_compute_segment_for_position(df_pos, position))

    if not segmented_parts:
        return pd.DataFrame()

    result = pd.concat(segmented_parts, axis=0)

    season_key = str(season)
    segment_col = f"SEGMENT_{season_key}"
    performance_score_col = f"PERFORMANCE_SCORE_{season_key}"
    sales_exp_col = f"SALES_EXPECTATION_PRICE_{season_key}"
    recommendation_col = f"RECOMMEND_FOR_ACTION_{season_key}"

    result[segment_col] = result["SEGMENT"]
    result[performance_score_col] = result["PERFORMANCE_SCORE"]
    result[sales_exp_col] = result[segment_col].map(_SALES_EXPECTATION_MAP)
    result[recommendation_col] = result[segment_col].map(_RECOMMEND_FOR_ACTION_MAP)

    final_total_df = result[
        ["PLAYER", "CLUB", segment_col, performance_score_col, sales_exp_col, recommendation_col]
    ].copy()

    # ONEMLI: Segment PLAYER+CLUB bazinda donuyor, yalnizca PLAYER bazinda
    # degil. Sezon ici kulup degistiren oyuncular (kiralik/transfer) iki
    # satirla temsil ediliyor: birinde gercek istatistikler, digerinde 0.
    # Sadece isimle eslestirince hangi satirin tutulacagi rastgele oluyor
    # ve orn. 1440 dakika oynayan bir defansci, ayni ismin 0 dakikalik
    # satirinin puanini alabiliyordu.
    final_total_df = final_total_df.drop_duplicates(subset=["PLAYER", "CLUB"], keep="first")
    return final_total_df