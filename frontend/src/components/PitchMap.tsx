"use client";

import { motion } from "framer-motion";
import type { SquadNeed } from "@/lib/api";

/**
 * PitchMap — bu arayuzun imza ogesi.
 *
 * Kadro ihtiyacini bir tablo satiri olarak degil, sahanin kendi uzerinde
 * gosterir: hangi BOLGE zayifsa o bolge yaniyor. "Defans zayif" bilgisi
 * zaten mekansal bir bilgi; onu mekansal olarak gostermek dogru olan.
 *
 * Isi rengi NEED_SCORE'a bagli: dusuk = sakin yesil, yuksek = alarm kirmizisi.
 */

type Props = {
  needs: SquadNeed[];
  selected: string | null;
  onSelect: (position: string) => void;
};

// Sahadaki dikey bolgeler (kaleci alani haric - proje kalecileri kapsamiyor)
const ZONES = [
  { pos: "DEFENDER", label: "Defans", y: 8, height: 28 },
  { pos: "MIDFIELD", label: "Orta saha", y: 36, height: 28 },
  { pos: "ATTACK", label: "Hucum", y: 64, height: 28 },
] as const;

function heatColor(score: number): string {
  // 0 -> saglikli yesil, 30+ -> alarm. Aradaki gecis amber uzerinden.
  const t = Math.min(score / 30, 1);
  if (t < 0.5) {
    const k = t / 0.5;
    return `rgba(${Math.round(52 + k * 203)}, ${Math.round(199 - k * 17)}, ${Math.round(89 - k * 50)}, ${0.14 + t * 0.3})`;
  }
  const k = (t - 0.5) / 0.5;
  return `rgba(255, ${Math.round(182 - k * 90)}, ${Math.round(39 + k * 53)}, ${0.14 + t * 0.34})`;
}

export default function PitchMap({ needs, selected, onSelect }: Props) {
  const byPos = new Map(needs.map((n) => [n.POSITION, n]));

  return (
    <div className="relative">
      <svg
        viewBox="0 0 100 100"
        className="w-full h-auto rounded-lg"
        style={{ background: "#0D1B27" }}
        role="img"
        aria-label="Kadro ihtiyacinin saha uzerinde isi haritasi"
      >
        {/* --- Isi bolgeleri --- */}
        {ZONES.map((zone, i) => {
          const need = byPos.get(zone.pos);
          const score = need?.NEED_SCORE ?? 0;
          const isSelected = selected === zone.pos;
          return (
            <motion.rect
              key={zone.pos}
              x={4}
              y={zone.y}
              width={92}
              height={zone.height}
              fill={heatColor(score)}
              stroke={isSelected ? "#FFB627" : "transparent"}
              strokeWidth={isSelected ? 0.6 : 0}
              className="cursor-pointer"
              onClick={() => onSelect(zone.pos)}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.15 * i, duration: 0.5 }}
              whileHover={{ opacity: 0.85 }}
            />
          );
        })}

        {/* --- Tebesir cizgileri: gercek saha isaretleri --- */}
        <g stroke="#4A6785" strokeWidth={0.4} fill="none" opacity={0.75}>
          <rect x={4} y={4} width={92} height={92} />
          <line x1={4} y1={50} x2={96} y2={50} />
          <circle cx={50} cy={50} r={11} />
          <circle cx={50} cy={50} r={0.9} fill="#4A6785" stroke="none" />
          {/* ceza sahalari */}
          <rect x={24} y={4} width={52} height={14} />
          <rect x={38} y={4} width={24} height={6} />
          <rect x={24} y={82} width={52} height={14} />
          <rect x={38} y={90} width={24} height={6} />
        </g>

        {/* --- Bolge etiketleri ve skorlar --- */}
        {ZONES.map((zone, i) => {
          const need = byPos.get(zone.pos);
          const score = need?.NEED_SCORE ?? 0;
          const cy = zone.y + zone.height / 2;
          return (
            <motion.g
              key={`${zone.pos}-label`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 + 0.12 * i, duration: 0.4 }}
              className="pointer-events-none"
            >
              <text
                x={9}
                y={cy - 1.5}
                fill="#E4EDF5"
                fontSize={4.2}
                fontFamily="var(--font-display)"
                letterSpacing="0.06em"
              >
                {zone.label.toUpperCase()}
              </text>
              <text
                x={9}
                y={cy + 4}
                fill="#7C93A8"
                fontSize={3}
                fontFamily="var(--font-body)"
              >
                {need ? `${need.SQUAD_COUNT} oyuncu · ort. ${need.AVG_AGE ?? "—"} yas` : ""}
              </text>
              <text
                x={91}
                y={cy + 1.5}
                fill={score >= 15 ? "#FFB627" : "#7C93A8"}
                fontSize={7}
                fontFamily="var(--font-data)"
                textAnchor="end"
              >
                {score.toFixed(0)}
              </text>
            </motion.g>
          );
        })}
      </svg>

      <p className="mt-3 text-xs text-chalk-dim">
        Sag taraftaki sayi <span className="text-chalk">ihtiyaç puanı</span> —
        performans açığı, kadro derinliği ve yaşlanma birlikte. Bir bölgeye
        tıklayarak o pozisyon için öneri alabilirsin.
      </p>
    </div>
  );
}
