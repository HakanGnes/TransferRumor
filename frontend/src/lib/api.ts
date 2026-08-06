/**
 * TransferRumor API istemcisi.
 * Backend: FastAPI (api.py), varsayilan olarak localhost:8100
 */

const BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export type League = {
  LEAGUE: string;
  teams: number;
  players: number;
  median_value: number | null;
  strength: number;
};

export type Team = {
  CLUB: string;
  LEAGUE: string;
  squad_size: number;
  avg_age: number;
  total_value: number | null;
};

export type SquadNeed = {
  POSITION: "ATTACK" | "MIDFIELD" | "DEFENDER";
  SQUAD_COUNT: number;
  AVG_PERFORMANCE: number;
  LEAGUE_AVG_PERFORMANCE: number;
  AVG_AGE: number | null;
  AGING_RATIO: number;
  NEED_SCORE: number;
};

export type TeamContext = {
  team: string;
  league: string | null;
  league_strength: number;
  squad_size: number;
  squad_total_value: number | null;
  squad_median_value: number | null;
  squad_max_value: number | null;
  avg_age: number;
};

export type Recommendation = {
  PLAYER: string;
  CLUB: string | null;
  LEAGUE: string | null;
  AGE: number | null;
  VALUE: number | null;
  quality: number | null;
  accessibility: number | null;
  overall: number | null;
  notes: string | null;
  affordability: number | null;
  league_pull: number | null;
  playing_time: number | null;
  age_factor: number | null;
};

export type RecommendationResponse = {
  team: string;
  season: number;
  target_position: string;
  current_level: number;
  context: TeamContext;
  squad_needs: SquadNeed[];
  recommendations: Recommendation[];
  disclaimer: string;
};

export type SquadPlayer = {
  PLAYER: string;
  POSITION: string | null;
  AGE: number | null;
  VALUE: number | null;
  APPEARANCES: number | null;
  MINUTES: number | null;
  GOALS: number | null;
  ASSISTS: number | null;
  RATING: number | null;
  segment: string | null;
  performance_score: string | null;
  sales_expectation: string | null;
  action: string | null;
};

export type SquadResponse = {
  team: string;
  season: number;
  squad_size: number;
  squad: SquadPlayer[];
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      `API ${res.status}: ${detail.slice(0, 200) || res.statusText}`
    );
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () =>
    get<{ status: string; seasons: number[]; player_count: number }>("/health"),

  leagues: () =>
    get<{ season: number; leagues: League[] }>("/leagues"),

  teams: (league?: string) =>
    get<{ season: number; teams: Team[] }>(
      `/teams${league ? `?league=${encodeURIComponent(league)}` : ""}`
    ),

  squad: (team: string) =>
    get<SquadResponse>(`/teams/${encodeURIComponent(team)}/squad`),

  recommendations: (
    team: string,
    opts: {
      position?: string;
      maxAge?: number;
      maxValue?: number;
      leagues?: string[];
      topN?: number;
    } = {}
  ) => {
    const p = new URLSearchParams();
    if (opts.position) p.set("position", opts.position);
    if (opts.maxAge) p.set("max_age", String(opts.maxAge));
    if (opts.maxValue) p.set("max_value", String(opts.maxValue));
    if (opts.topN) p.set("top_n", String(opts.topN));
    opts.leagues?.forEach((l) => p.append("leagues", l));
    return get<RecommendationResponse>(
      `/teams/${encodeURIComponent(team)}/recommendations?${p.toString()}`
    );
  },
};

/** Piyasa degerini kisa ve okunur bicimde yazar: 12.5M / 750K */
export function formatValue(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (v >= 1_000_000) return `€${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `€${Math.round(v / 1_000)}K`;
  return `€${Math.round(v)}`;
}
