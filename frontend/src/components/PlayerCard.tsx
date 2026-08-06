"use client";

import { motion } from "framer-motion";
import { formatValue, type Recommendation } from "@/lib/api";

/**
 * Bir transfer hedefini, skorunun NEDEN o oldugunu gostererek sunar.
 * Tek bir "%78" sayisi guven vermez; bilesenleri acmak hem seffaf hem
 * de kullaniciya karar verme payi birakiyor.
 */

const FACTORS = [
  { key: "affordability", label: "Bütçe uygunluğu", weight: "%40" },
  { key: "league_pull", label: "Lig cazibesi", weight: "%25" },
  { key: "playing_time", label: "Forma süresi", weight: "%20" },
  { key: "age_factor", label: "Yaş", weight: "%15" },
] as const;

export default function PlayerCard({
  player,
  rank,
  expanded,
  onToggle,
}: {
  player: Recommendation;
  rank: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const overall = player.overall ?? 0;

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(rank * 0.04, 0.4) }}
      className="border border-line bg-pitch-surface rounded-lg overflow-hidden hover:border-[#2E4A66] transition-colors"
    >
      <button
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full text-left p-4 flex items-center gap-4"
      >
        {/* Siralama numarasi - forma numarasi gibi */}
        <span className="display text-2xl text-chalk-dim w-8 shrink-0 tabular-nums">
          {String(rank + 1).padStart(2, "0")}
        </span>

        <div className="min-w-0 flex-1">
          <h3 className="display text-lg text-chalk leading-tight truncate">
            {player.PLAYER}
          </h3>
          <p className="text-xs text-chalk-dim truncate">
            {player.CLUB} · {player.LEAGUE} · {player.AGE ?? "—"} yaş
          </p>
        </div>

        <div className="text-right shrink-0">
          <div className="data text-sm text-chalk">{formatValue(player.VALUE)}</div>
          <div className="text-[11px] text-chalk-dim">piyasa değeri</div>
        </div>

        {/* Genel skor - projektor renginde */}
        <div className="text-right shrink-0 w-16">
          <div className="data text-2xl text-floodlight leading-none">
            {overall.toFixed(0)}
          </div>
          <div className="text-[11px] text-chalk-dim">genel</div>
        </div>
      </button>

      {expanded && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="border-t border-line px-4 pb-4 pt-3"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-xs text-chalk-dim mb-2">
                Ulaşılabilirlik bileşenleri
              </p>
              <div className="space-y-2">
                {FACTORS.map((f, i) => {
                  const v = (player[f.key] as number | null) ?? 0;
                  return (
                    <div key={f.key}>
                      <div className="flex justify-between text-[11px] mb-1">
                        <span className="text-chalk-dim">
                          {f.label}{" "}
                          <span className="opacity-50">{f.weight}</span>
                        </span>
                        <span className="data text-chalk">{v.toFixed(0)}</span>
                      </div>
                      <div className="h-1.5 bg-pitch-deep rounded-full overflow-hidden">
                        <motion.div
                          className="h-full rounded-full"
                          style={{
                            background:
                              v >= 60 ? "var(--grass)" : v >= 35 ? "var(--floodlight)" : "var(--alarm)",
                          }}
                          initial={{ width: 0 }}
                          animate={{ width: `${v}%` }}
                          transition={{ duration: 0.5, delay: 0.05 * i }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <p className="text-xs text-chalk-dim mb-1">Kalite (lig düzeltilmiş)</p>
                <p className="data text-xl text-chalk">
                  {player.quality?.toFixed(2) ?? "—"}
                </p>
              </div>
              {player.notes && (
                <div>
                  <p className="text-xs text-chalk-dim mb-1">Not</p>
                  <p className="text-sm text-chalk leading-snug">{player.notes}</p>
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </motion.article>
  );
}
