import type { BandPerf, Cell, Day, DayIndexEntry } from "../data";
import { BAND_LABEL, fmtDate, pct, plusDays } from "../data";

export function Legend({ reveal }: { reveal: boolean }) {
  return (
    <div className="legend" aria-label="Map legend">
      <div className="legend-row"><span className="sw obs" />Fire seen by satellite on this day</div>
      <div className="legend-row"><span className="sw high" /><b>High</b>&nbsp;chance a fire seen the day before is still burning</div>
      <div className="legend-row"><span className="sw medium" /><b>Medium</b>&nbsp;chance</div>
      <div className="legend-row"><span className="sw low" /><b>Low</b>&nbsp;chance</div>
      {reveal && <div className="small muted">Faded circles: no fire was detected there that day.</div>}
    </div>
  );
}

export function TodaySummary({ day, entry, perf }: { day: Day; entry?: DayIndexEntry; perf?: BandPerf[] }) {
  const high = day.cells.filter((c) => c.band === "high").length;
  const highRate = perf?.find((b) => b.band === "high")?.observed_rate;
  return (
    <div className="card">
      <h2>{fmtDate(day.date, { weekday: "long", day: "numeric", month: "long" })}</h2>
      <div className="stats">
        <div className="stat"><div className="v">{day.detections.length.toLocaleString("en-IN")}</div><div className="k">fire detections</div></div>
        <div className="stat"><div className="v">{day.cells.length.toLocaleString("en-IN")}</div><div className="k">areas with fire the day before</div></div>
        <div className="stat"><div className="v">{high.toLocaleString("en-IN")}</div><div className="k">high-chance areas</div></div>
      </div>
      <p className="small muted" style={{ margin: "10px 0 0" }}>
        Each area is about 11 × 11 km. {highRate != null && <>In past tests, <b>{pct(highRate)}</b> of areas marked high were still burning the next day.</>}
        {entry?.outcomes_final && entry.high_burned_again != null && <> On this day, <b>{pct(entry.high_burned_again)}</b> of high areas burned again.</>}
      </p>
    </div>
  );
}

export function AreaCard({ cell, date, perf, onClose }: { cell: Cell; date: string; perf?: BandPerf[]; onClose: () => void }) {
  const rate = perf?.find((b) => b.band === cell.band)?.observed_rate;
  const prev = fmtDate(plusDays(date, -1));
  return (
    <div className="card area" aria-live="polite">
      <button className="close" onClick={onClose} aria-label="Close area details">×</button>
      <h2>{cell.state ?? "Area"} <span className={`pill ${cell.band}`}>{BAND_LABEL[cell.band]} chance</span></h2>
      <p className="lede">
        Fire was detected here on <b>{prev}</b> ({cell.detectionsPrevDay} satellite detection{cell.detectionsPrevDay === 1 ? "" : "s"}).
        The model gives a <b>{BAND_LABEL[cell.band].toLowerCase()}</b> chance ({pct(cell.p)}) that it was still burning on <b>{fmtDate(date)}</b>.
      </p>
      {rate != null && <p className="small muted">In past tests, {pct(rate)} of areas in the {cell.band} band burned again the next day.</p>}
      <p className="small" style={{ marginBottom: 6 }}>
        {cell.burnedAgain == null ? "Outcome: not known yet (the day is not over or data is still arriving)."
          : cell.burnedAgain === 1 ? "Outcome: fire was detected here again." : "Outcome: no fire was detected here (clouds can hide fires)."}
      </p>
      <details>
        <summary className="small">Details</summary>
        <dl className="kv">
          <dt>Area</dt><dd>{cell.id} · {cell.lat.toFixed(2)}°N {cell.lon.toFixed(2)}°E</dd>
          <dt>Probability</dt><dd>{cell.p.toFixed(3)}</dd>
          <dt>Fire power day before</dt><dd>{cell.frpPrevDay.toFixed(1)} MW (sum)</dd>
        </dl>
      </details>
    </div>
  );
}

export function DayStrip({ days, selected, onPick }: { days: DayIndexEntry[]; selected: string; onPick: (d: string) => void }) {
  const max = Math.max(1, ...days.map((d) => d.detections));
  return (
    <div>
      <div className="strip" role="group" aria-label="Pick a day">
        {days.map((d) => (
          <button key={d.date} className={d.unobserved ? "gap" : ""} aria-pressed={d.date === selected}
            title={`${fmtDate(d.date)}: ${d.detections} detections${d.unobserved ? " (satellite outage)" : ""}`}
            style={{ height: `${Math.max(6, (d.detections / max) * 100)}%` }} onClick={() => onPick(d.date)} />
        ))}
      </div>
      <div className="row small muted" style={{ justifyContent: "space-between" }}>
        <span>{days[0] && fmtDate(days[0].date)}</span><span>daily fire detections</span><span>{days.at(-1) && fmtDate(days.at(-1)!.date)}</span>
      </div>
    </div>
  );
}

export function StateList({ day, onPick }: { day: Day; onPick: (s: string) => void }) {
  const by = new Map<string, { det: number; high: number; cells: number }>();
  for (const c of day.cells) {
    const k = c.state ?? "Unknown";
    const v = by.get(k) ?? { det: 0, high: 0, cells: 0 };
    v.cells++; if (c.band === "high") v.high++;
    by.set(k, v);
  }
  const rows = [...by.entries()].sort((a, b) => b[1].high - a[1].high || b[1].cells - a[1].cells).slice(0, 10);
  if (!rows.length) return null;
  return (
    <div className="card">
      <h2>Where to look</h2>
      <ul className="list">
        {rows.map(([s, v]) => (
          <li key={s}><button onClick={() => onPick(s)}><span>{s}</span>
            <span className="num">{v.high} high · {v.cells} areas</span></button></li>
        ))}
      </ul>
    </div>
  );
}
