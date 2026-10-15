// Typed access to the static data contract (terrasentinel.site.v1, docs/plan_v1.md §4).

export type Band = "low" | "medium" | "high";

export interface BandDef { band: Band; p_min: number; p_max: number }
export interface BandPerf { band: Band; p_min: number; p_max: number; cell_days: number; share: number; observed_rate: number | null }

export interface Meta {
  schema: string;
  generated_at_utc: string;
  pipeline_run_at_utc: string;
  latest_acquisition_utc: Record<string, string>;
  data_as_of_utc: string | null;
  stale_after_hours: number;
  latest_day: string | null;
  model: { id: string; sha256: string; bands: BandDef[]; horizon: string; trained_on: string };
  sources: string[];
  unobserved_days: string[];
  disclaimer: string;
}

export interface DayIndexEntry {
  date: string; detections: number; cells: number; high: number;
  outcomes_final: boolean; unobserved: boolean; high_burned_again: number | null;
}

export interface Cell {
  id: string; lat: number; lon: number; state: string | null; p: number; band: Band;
  detectionsPrevDay: number; frpPrevDay: number; burnedAgain: 0 | 1 | null;
}
export interface Detection { lat: number; lon: number; hhmm: string; frp: number; satellite: string }
export interface Day { date: string; outcomesFinal: boolean; unobserved: boolean; cells: Cell[]; detections: Detection[] }

export interface StateSeries { [state: string]: [string, number, number, number][] }  // date, detections, cells, high

export interface Results {
  study: string;
  primary: { comparison: string; metric: string; difference: number; ci95: [number, number]; conclusion: string };
  test_2024: { set: string; prevalence: number; seasonal_B0: number; B1: number; M2: number }[];
  b1_vs_seasonal: { set: string; difference: number; ci95: [number, number] }[];
  bands: Record<"val" | "test" | "geo_test", BandPerf[]>;
  validation: { name: string; finding: string; independence: string }[];
}

const SCHEMA = "terrasentinel.site.v1";
const cache = new Map<string, Promise<unknown>>();

function get<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(path, fetch(`./data/${path}`, { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(path) as Promise<T>;
}

export async function loadMeta(): Promise<Meta> {
  const m = await get<Meta>("meta.json");
  if (m.schema !== SCHEMA) throw new Error(`Unsupported data schema ${m.schema}`);
  return m;
}
export const loadIndex = () => get<{ days: DayIndexEntry[] }>("index.json").then((x) => x.days);
export const loadStates = () => get<{ states: StateSeries }>("states.json").then((x) => x.states);
export const loadResults = () => get<Results>("results.json");
export const loadStateShapes = () => get<GeoJSON.FeatureCollection>("states.geojson");

export async function loadDay(date: string): Promise<Day> {
  const raw = await get<{
    date: string; outcomes_final: boolean; unobserved: boolean;
    cells: [string, number, number, string | null, number, Band, number, number, 0 | 1 | null][];
    detections: [number, number, string, number, string][];
  }>(`days/${date}.json`);
  return {
    date: raw.date, outcomesFinal: raw.outcomes_final, unobserved: raw.unobserved,
    cells: raw.cells.map(([id, lat, lon, state, p, band, d, f, b]) => ({
      id, lat, lon, state, p, band, detectionsPrevDay: d, frpPrevDay: f, burnedAgain: b,
    })),
    detections: raw.detections.map(([lat, lon, hhmm, frp, satellite]) => ({ lat, lon, hhmm, frp, satellite })),
  };
}

// ---------- formatting helpers ----------
export const BAND_LABEL: Record<Band, string> = { high: "High", medium: "Medium", low: "Low" };

export function hoursSince(iso: string | null): number | null {
  return iso ? (Date.now() - new Date(iso).getTime()) / 3.6e6 : null;
}

export function fmtDate(d: string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }): string {
  return new Date(`${d}T00:00:00Z`).toLocaleDateString("en-IN", { timeZone: "UTC", ...opts });
}

export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { timeZone: "UTC", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }) + " UTC";
}

export function pct(x: number | null | undefined, digits = 0): string {
  return x == null ? "—" : `${(x * 100).toFixed(digits)}%`;
}

export function plusDays(d: string, n: number): string {
  const t = new Date(`${d}T00:00:00Z`);
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}
