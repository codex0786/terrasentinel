import { useCallback, useEffect, useState } from "react";
import type { DayIndexEntry, Meta, Results, StateSeries } from "./data";
import { fmtDateTime, hoursSince, loadIndex, loadMeta, loadResults, loadStates, loadStateShapes } from "./data";
import AboutPage from "./pages/AboutPage";
import TodayPage from "./pages/TodayPage";

// Hash routes (work on GitHub Pages): #/?date=YYYY-MM-DD&state=Name  ·  #/about
interface Route { page: "today" | "about"; date: string | null; state: string | null }

function parse(): Route {
  const [path, query = ""] = window.location.hash.replace(/^#/, "").split("?");
  const q = new URLSearchParams(query);
  return { page: path === "/about" ? "about" : "today", date: q.get("date"), state: q.get("state") };
}

function useDark(): boolean {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const [dark, setDark] = useState(mq.matches);
  useEffect(() => {
    const f = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, [mq]);
  return dark;
}

interface Data { meta: Meta; index: DayIndexEntry[]; results: Results; states: StateSeries; shapes: GeoJSON.FeatureCollection }

export default function App() {
  const [route, setRoute] = useState<Route>(parse);
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const dark = useDark();

  useEffect(() => {
    const f = () => setRoute(parse());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);

  useEffect(() => {
    Promise.all([loadMeta(), loadIndex(), loadResults(), loadStates(), loadStateShapes()])
      .then(([meta, index, results, states, shapes]) => setData({ meta, index, results, states, shapes }))
      .catch((e) => setErr(String(e)));
  }, []);

  const navigate = useCallback((q: { date?: string; state?: string | null }) => {
    const cur = parse();
    const params = new URLSearchParams();
    const date = q.date ?? cur.date;
    const state = q.state === undefined ? cur.state : q.state;
    if (date && date !== data?.meta.latest_day) params.set("date", date);
    if (state) params.set("state", state);
    const s = params.toString();
    window.location.hash = `/${s ? `?${s}` : ""}`;
  }, [data]);

  const age = data ? hoursSince(data.meta.data_as_of_utc) : null;
  const stale = data && age != null && age > data.meta.stale_after_hours;

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/"><span className="brand-dot" aria-hidden />TerraSentinel <small>India fire watch</small></a>
        {data?.meta.data_as_of_utc && (
          <span className="fresh" title={`Pipeline ran ${fmtDateTime(data.meta.pipeline_run_at_utc)}`}>
            Latest satellite data: {fmtDateTime(data.meta.data_as_of_utc)}
          </span>
        )}
        <nav className="nav" aria-label="Main">
          <a href="#/" aria-current={route.page === "today" ? "page" : undefined}>Map</a>
          <a href="#/about" aria-current={route.page === "about" ? "page" : undefined}>How it works</a>
        </nav>
      </header>
      <div>
        {stale && <div className="banner warn" role="status">This data is {Math.round(age!)} hours old. The daily update may have failed, so treat it as out of date.</div>}
        {err && <div className="banner err" role="alert">Could not load data: {err}</div>}
      </div>
      {!data ? <div className="loading">{err ? "Data unavailable." : "Loading…"}</div>
        : route.page === "about" ? <AboutPage meta={data.meta} results={data.results} />
          : <TodayPage {...data} date={route.date && data.index.some((d) => d.date === route.date) ? route.date : data.meta.latest_day!}
            state={route.state} dark={dark} navigate={navigate} />}
      <footer className="footer"><strong>Not an official warning.</strong> In an emergency contact local authorities
        (NDMA helpline <a href="tel:1078">1078</a>, State Forest Departments, <a href="https://mausam.imd.gov.in/">IMD</a>). Research prototype.</footer>
    </div>
  );
}
