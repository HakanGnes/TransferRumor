"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import PitchMap from "@/components/PitchMap";
import PlayerCard from "@/components/PlayerCard";
import SquadReview from "@/components/SquadReview";
import {
  api,
  formatValue,
  type League,
  type RecommendationResponse,
  type SquadPlayer,
  type Team,
} from "@/lib/api";

export default function Home() {
  const [leagues, setLeagues] = useState<League[]>([]);
  const [league, setLeague] = useState<string>("");
  const [teams, setTeams] = useState<Team[]>([]);
  const [team, setTeam] = useState<string>("");

  const [maxValueM, setMaxValueM] = useState(50);
  const [maxAge, setMaxAge] = useState(32);
  const [position, setPosition] = useState<string | null>(null);

  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openCard, setOpenCard] = useState<number | null>(null);
  const [squad, setSquad] = useState<SquadPlayer[] | null>(null);
  const [tab, setTab] = useState<"targets" | "squad">("targets");

  useEffect(() => {
    api
      .leagues()
      .then((r) => {
        setLeagues(r.leagues);
        if (r.leagues.length) setLeague(r.leagues[0].LEAGUE);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!league) return;
    setTeam("");
    setData(null);
    api
      .teams(league)
      .then((r) => setTeams(r.teams))
      .catch((e) => setError(e.message));
  }, [league]);

  async function runAnalysis(pos?: string | null) {
    if (!team) return;
    setLoading(true);
    setError(null);
    setOpenCard(null);
    try {
      const res = await api.recommendations(team, {
        position: pos ?? undefined,
        maxAge,
        maxValue: maxValueM * 1_000_000,
        topN: 12,
      });
      setData(res);
      setPosition(res.target_position);
      const sq = await api.squad(team);
      setSquad(sq.squad);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bilinmeyen hata");
      setData(null);
      setSquad(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen">
      <header className="border-b border-line">
        <div className="mx-auto max-w-6xl px-5 py-10 sm:py-14">
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-xs tracking-[0.25em] text-floodlight display mb-3"
          >
            Scouting &amp; Transfer Analysis
          </motion.p>
          <motion.h1
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="display text-5xl sm:text-7xl leading-[0.92] text-chalk max-w-3xl"
          >
            Kadronun neresi <span className="text-floodlight">zayıfsa</span>{" "}
            transfer oradan başlar
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="mt-5 text-chalk-dim max-w-xl leading-relaxed"
          >
            12 ligden 8.800+ oyuncunun performansı, pozisyon bazlı
            değerlendiriliyor. Takımını seç; hangi bölgenin takviye istediğini
            sahada gör, bütçene uyan ulaşılabilir hedefleri sırala.
          </motion.p>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-5 py-8">
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
          <Field label="Lig">
            <select
              value={league}
              onChange={(e) => setLeague(e.target.value)}
              className="w-full bg-pitch-surface border border-line rounded px-3 py-2 text-sm text-chalk"
            >
              {leagues.map((l) => (
                <option key={l.LEAGUE} value={l.LEAGUE}>
                  {l.LEAGUE}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Takım">
            <select
              value={team}
              onChange={(e) => setTeam(e.target.value)}
              className="w-full bg-pitch-surface border border-line rounded px-3 py-2 text-sm text-chalk"
            >
              <option value="">Takım seç…</option>
              {teams.map((t) => (
                <option key={t.CLUB} value={t.CLUB}>
                  {t.CLUB}
                </option>
              ))}
            </select>
          </Field>

          <Field label={`Bütçe tavanı — €${maxValueM}M`}>
            <input
              type="range"
              min={1}
              max={500}
              value={maxValueM}
              onChange={(e) => setMaxValueM(Number(e.target.value))}
              className="w-full accent-[#FFB627]"
            />
          </Field>

          <Field label={`Yaş üst sınırı — ${maxAge}`}>
            <input
              type="range"
              min={18}
              max={40}
              value={maxAge}
              onChange={(e) => setMaxAge(Number(e.target.value))}
              className="w-full accent-[#FFB627]"
            />
          </Field>
        </section>

        <button
          onClick={() => runAnalysis(null)}
          disabled={!team || loading}
          className="display tracking-wider px-6 py-3 rounded bg-floodlight text-[#0A1520] font-semibold disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-110 transition"
        >
          {loading ? "Analiz ediliyor…" : "Kadroyu analiz et"}
        </button>

        {error && (
          <div className="mt-6 border border-alarm/40 bg-alarm/10 rounded-lg p-4">
            <p className="text-alarm text-sm font-medium mb-1">
              API&apos;ye bağlanılamadı
            </p>
            <p className="text-chalk-dim text-xs leading-relaxed">
              {error}
              <br />
              Backend&apos;in çalıştığından emin ol:{" "}
              <code className="data text-chalk">uvicorn api:app --port 8100</code>
            </p>
          </div>
        )}

        <AnimatePresence mode="wait">
          {data && (
            <motion.div
              key={data.team + data.target_position}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,380px)_1fr]"
            >
              <div>
                <h2 className="display text-2xl text-chalk mb-1">{data.team}</h2>
                <p className="text-xs text-chalk-dim mb-4">
                  {data.context.league} · {data.context.squad_size} oyuncu · ort.{" "}
                  {data.context.avg_age.toFixed(1)} yaş · kadro değeri{" "}
                  {formatValue(data.context.squad_total_value)}
                </p>

                <PitchMap
                  needs={data.squad_needs}
                  selected={position}
                  onSelect={(p) => {
                    setPosition(p);
                    runAnalysis(p);
                  }}
                />
              </div>

              <div>
                {/* Sekmeler: disaridan transfer vs elindeki kadro */}
                <div className="flex gap-1 mb-4 border-b border-line">
                  {([
                    ["targets", `${data.target_position} hedefleri`],
                    ["squad", "Kadro değerlendirmesi"],
                  ] as const).map(([key, label]) => (
                    <button
                      key={key}
                      onClick={() => setTab(key)}
                      className={`display text-sm tracking-wide px-4 py-2.5 border-b-2 -mb-px transition-colors ${
                        tab === key
                          ? "border-floodlight text-floodlight"
                          : "border-transparent text-chalk-dim hover:text-chalk"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                {tab === "squad" ? (
                  squad ? (
                    <SquadReview squad={squad} />
                  ) : (
                    <p className="text-sm text-chalk-dim">Kadro yükleniyor…</p>
                  )
                ) : (
                <>
                <p className="text-xs text-chalk-dim mb-5">
                  Takımın bu pozisyondaki mevcut seviyesi{" "}
                  <span className="data text-chalk">{data.current_level}</span> —
                  yalnızca bunun üzerindeki oyuncular listeleniyor.
                </p>

                {data.recommendations.length === 0 ? (
                  <div className="border border-line rounded-lg p-8 text-center">
                    <p className="text-chalk mb-1">
                      Bu kriterlere uyan oyuncu yok
                    </p>
                    <p className="text-chalk-dim text-sm">
                      Bütçe tavanını veya yaş sınırını yükseltmeyi dene.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {data.recommendations.map((p, i) => (
                      <PlayerCard
                        key={`${p.PLAYER}-${p.CLUB}`}
                        player={p}
                        rank={i}
                        expanded={openCard === i}
                        onToggle={() => setOpenCard(openCard === i ? null : i)}
                      />
                    ))}
                  </div>
                )}

                </>
                )}

                <details className="mt-6 border border-line rounded-lg">
                  <summary className="px-4 py-3 cursor-pointer text-sm text-chalk-dim hover:text-chalk">
                    Bu skorlar nasıl hesaplanıyor? Neyi bilmiyor?
                  </summary>
                  <div className="px-4 pb-4 text-xs text-chalk-dim leading-relaxed space-y-2">
                    <p>
                      <span className="text-chalk">Kalite</span> — oyuncunun
                      pozisyonundaki performans skoru, ligin gücüne göre
                      düzeltilmiş.
                    </p>
                    <p>
                      <span className="text-chalk">Ulaşılabilirlik</span> — bütçe
                      uygunluğu, lig cazibesi, forma süresi ve yaştan oluşan
                      kurallara dayalı bir gösterge.
                    </p>
                    <p className="text-alarm/90 pt-1">{data.disclaimer}</p>
                  </div>
                </details>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <footer className="border-t border-line mt-16">
        <div className="mx-auto max-w-6xl px-5 py-6 text-xs text-chalk-dim">
          İstatistikler API-Football (2024 sezonu) · Piyasa değerleri
          Transfermarkt · Kişisel/eğitim amaçlı proje
        </div>
      </footer>
    </main>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-[11px] tracking-wider text-chalk-dim mb-2 display">
        {label}
      </span>
      {children}
    </label>
  );
}
