"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { formatValue, type SquadPlayer } from "@/lib/api";

/**
 * Takimin KENDI oyuncularini degerlendirir: her oyuncunun segmenti,
 * performans skoru, satis beklentisi ve o segment icin aksiyon onerisi.
 *
 * Transfer onerisi "disaridan kimi al" sorusunu cevapliyor; bu bolum
 * "elindekilerle ne yap" sorusunu.
 */

const POSITION_LABELS: Record<string, string> = {
  DEFENDER: "Defans",
  MIDFIELD: "Orta saha",
  ATTACK: "Hücum",
};

/** Segment adindan renk tonu: performans seviyesine gore */
function segmentTone(score: string | number | null): string {
  const s = Number(score);
  if (s >= 5) return "var(--grass)";
  if (s >= 4) return "#8FD14F";
  if (s >= 3) return "var(--floodlight)";
  if (s >= 2) return "#FF8C42";
  return "var(--alarm)";
}

function prettySegment(seg: string | null): string {
  if (!seg) return "—";
  return seg.replace(/_/g, " ");
}

export default function SquadReview({ squad }: { squad: SquadPlayer[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const [onlyPlayed, setOnlyPlayed] = useState(true);

  const filtered = onlyPlayed
    ? squad.filter((p) => (p.MINUTES ?? 0) > 0)
    : squad;

  const groups = ["DEFENDER", "MIDFIELD", "ATTACK"].map((pos) => ({
    pos,
    players: filtered.filter((p) => p.POSITION === pos),
  }));

  const benched = squad.length - filtered.length;

  return (
    <div>
      <div className="flex items-center justify-between gap-4 mb-4">
        <p className="text-xs text-chalk-dim">
          {filtered.length} oyuncu değerlendirildi
        </p>
        {benched > 0 && (
          <label className="flex items-center gap-2 text-xs text-chalk-dim cursor-pointer">
            <input
              type="checkbox"
              checked={onlyPlayed}
              onChange={(e) => setOnlyPlayed(e.target.checked)}
              className="accent-[#FFB627]"
            />
            Sahaya çıkmayan {benched} oyuncuyu gizle
          </label>
        )}
      </div>

      <div className="space-y-6">
        {groups.map(({ pos, players }) => (
          <section key={pos}>
            <h3 className="display text-sm tracking-widest text-chalk-dim mb-2">
              {POSITION_LABELS[pos]}{" "}
              <span className="opacity-50">({players.length})</span>
            </h3>

            {players.length === 0 ? (
              <p className="text-xs text-chalk-dim italic">
                Bu pozisyonda değerlendirilecek oyuncu yok.
              </p>
            ) : (
              <div className="space-y-1.5">
                {players.map((p, i) => {
                  const key = `${pos}-${p.PLAYER}`;
                  const isOpen = open === key;
                  return (
                    <motion.div
                      key={key}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: Math.min(i * 0.02, 0.3) }}
                      className="border border-line bg-pitch-surface rounded overflow-hidden"
                    >
                      <button
                        onClick={() => setOpen(isOpen ? null : key)}
                        aria-expanded={isOpen}
                        className="w-full text-left px-3 py-2.5 flex items-center gap-3"
                      >
                        <span
                          className="w-1 h-8 rounded-full shrink-0"
                          style={{ background: segmentTone(p.performance_score) }}
                          aria-hidden
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-chalk truncate">{p.PLAYER}</p>
                          <p className="text-[11px] text-chalk-dim truncate">
                            {prettySegment(p.segment)}
                          </p>
                        </div>
                        <div className="text-right shrink-0 hidden sm:block">
                          <p className="data text-[11px] text-chalk-dim">
                            {p.MINUTES ?? 0}&apos;
                          </p>
                          <p className="text-[10px] text-chalk-dim">süre</p>
                        </div>
                        <div className="text-right shrink-0 w-16">
                          <p className="data text-sm text-chalk">
                            {formatValue(p.VALUE)}
                          </p>
                          <p className="text-[10px] text-chalk-dim">
                            {p.sales_expectation ?? "—"}
                          </p>
                        </div>
                      </button>

                      {isOpen && p.action && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          className="border-t border-line px-3 py-3"
                        >
                          <p className="text-[11px] tracking-wider text-floodlight display mb-1.5">
                            Önerilen aksiyon
                          </p>
                          <p className="text-sm text-chalk-dim leading-relaxed">
                            {p.action}
                          </p>
                          <div className="mt-3 flex gap-5 text-[11px] text-chalk-dim">
                            <span>
                              Yaş <span className="data text-chalk">{p.AGE ?? "—"}</span>
                            </span>
                            <span>
                              Maç{" "}
                              <span className="data text-chalk">
                                {p.APPEARANCES ?? 0}
                              </span>
                            </span>
                            <span>
                              G/A{" "}
                              <span className="data text-chalk">
                                {p.GOALS ?? 0}/{p.ASSISTS ?? 0}
                              </span>
                            </span>
                          </div>
                        </motion.div>
                      )}
                    </motion.div>
                  );
                })}
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
