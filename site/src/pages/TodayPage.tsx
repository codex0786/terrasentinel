import { useEffect, useMemo, useState } from "react";
import MapView from "../components/MapView";
import { AreaCard, DayStrip, Legend, StateList, TodaySummary } from "../components/Panels";
import type { Day, DayIndexEntry, Meta, Results, StateSeries } from "../data";
import { fmtDate, loadDay } from "../data";

interface Props {
  meta: Meta; index: DayIndexEntry[]; results: Results; states: StateSeries;
  shapes: GeoJSON.FeatureCollection; date: string; state: string | null; dark: boolean;
  navigate: (q: { date?: string; state?: string | null }) => void;
}

export default function TodayPage(p: Props) {
  const [day, setDay] = useState<Day | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cellId, setCellId] = useState<string | null>(null);
  const [showObs, setShowObs] = useState(true);
  const [showPred, setShowPred] = useState(true);
  const [onlyHigh, setOnlyHigh] = useState(false);
  const [reveal, setReveal] = useState(false);

  useEffect(() => {
    setErr(null); setCellId(null);
    loadDay(p.date).then(setDay).catch((e) => setErr(String(e)));
  }, [p.date]);

  const entry = p.index.find((d) => d.date === p.date);
  const isLatest = p.date === p.meta.latest_day;
  const cell = useMemo(() => day?.cells.find((c) => c.id === cellId) ?? null, [day, cellId]);
  const perf = p.results.bands.test;
  const stateSeries = p.state ? p.states[p.state] : undefined;
  const stateToday = stateSeries?.find((r) => r[0] === p.date);

  return (
    <div className="main">
      <aside className="side" aria-label="Summary and controls">
        <div className="card">
          <p className="lede">
            {isLatest ? "Where fires were seen in India, and where they are likely to still be burning."
              : `Fires and predictions for ${fmtDate(p.date, { day: "numeric", month: "long", year: "numeric" })}.`}
          </p>
          <div className="row" style={{ marginTop: 10 }}>
            <label className="small muted" htmlFor="state">State</label>
            <select id="state" className="btn" value={p.state ?? ""} onChange={(e) => p.navigate({ state: e.target.value || null })}>
              <option value="">All India</option>
              {Object.keys(p.states).sort().map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            {!isLatest && <button className="btn" onClick={() => p.navigate({ date: p.meta.latest_day! })}>Back to latest</button>}
          </div>
        </div>

        {err && <div className="banner err">Could not load this day ({err}).</div>}
        {entry?.unobserved && <div className="banner warn">A satellite recorded no data over India this day, so there are no predictions.</div>}
        {day && <TodaySummary day={day} entry={entry} perf={perf} />}
        {p.state && stateToday && (
          <div className="card">
            <h2>{p.state}</h2>
            <p className="small" style={{ margin: 0 }}>{stateToday[1]} detections · {stateToday[2]} areas watched · <b>{stateToday[3]} high</b></p>
          </div>
        )}
        {cell && day && <AreaCard cell={cell} date={day.date} perf={perf} onClose={() => setCellId(null)} />}

        <div className="card">
          <h2>Map layers</h2>
          <Legend reveal={reveal} />
          <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
            <label className="check"><input type="checkbox" checked={showObs} onChange={(e) => setShowObs(e.target.checked)} />Fires seen</label>
            <label className="check"><input type="checkbox" checked={showPred} onChange={(e) => setShowPred(e.target.checked)} />Chance of continuing</label>
            <label className="check"><input type="checkbox" checked={onlyHigh} onChange={(e) => setOnlyHigh(e.target.checked)} />Only high-chance areas</label>
            <label className="check"><input type="checkbox" checked={reveal} disabled={!day?.outcomesFinal}
              onChange={(e) => setReveal(e.target.checked)} />Show what actually happened{!day?.outcomesFinal && " (after the day ends)"}</label>
          </div>
        </div>

        <div className="card">
          <h2>Past days</h2>
          <DayStrip days={p.index} selected={p.date} onPick={(d) => p.navigate({ date: d })} />
        </div>

        {day && <StateList day={day} onPick={(s) => p.navigate({ state: s })} />}
      </aside>
      <div className="mapwrap">
        <MapView day={day} shapes={p.shapes} selectedState={p.state} selectedCell={cellId}
          showObs={showObs} showPred={showPred} onlyHigh={onlyHigh} reveal={reveal} dark={p.dark}
          onSelectCell={setCellId} onSelectState={(s) => p.navigate({ state: s })} />
        {!day && !err && <div className="loading">Loading map data…</div>}
        <div className="map-note">Tap a blue circle for details. Predictions cover only places where fire was seen the day before.</div>
      </div>
    </div>
  );
}
