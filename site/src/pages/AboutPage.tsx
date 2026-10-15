import type { Meta, Results } from "../data";
import { pct } from "../data";

const f3 = (x: number) => x.toFixed(3);
const ci = (c: [number, number]) => `${c[0] >= 0 ? "+" : ""}${c[0].toFixed(3)} to ${c[1] >= 0 ? "+" : ""}${c[1].toFixed(3)}`;

export default function AboutPage({ meta, results }: { meta: Meta; results: Results }) {
  return (
    <div className="page">
      <div className="prose">
        <h1>How TerraSentinel works</h1>
        <p className="callout">{meta.disclaimer}</p>

        <h2>What you are looking at</h2>
        <p>NASA satellites (VIIRS on Suomi-NPP and NOAA-20) pass over India several times a day and record
          places that are unusually hot: usually fires, sometimes industrial heat. These appear as
          <b> orange dots</b>. Data arrives about 3 hours after each pass.</p>
        <p>For every 11 × 11 km area where fire was seen on one day, a statistical model estimates the chance
          that fire is detected there again the next day. These appear as <b>blue circles</b>: darker means
          more likely. The model only covers places that already had fire; it does <b>not</b> predict where new
          fires will start.</p>

        <h2>How good is it?</h2>
        <p>The method was fixed in advance and tested once on a year it had never seen (2024), including in three
          states it was never trained on. Areas are grouped into three bands:</p>
        <table>
          <thead><tr><th>Band</th><th>Share of areas</th><th>Burned again (2024 test)</th><th>Held-out states</th></tr></thead>
          <tbody>
            {results.bands.test.map((b, i) => (
              <tr key={b.band}><td><span className={`pill ${b.band}`}>{b.band}</span></td>
                <td className="n">{pct(b.share)}</td><td className="n">{pct(b.observed_rate)}</td>
                <td className="n">{pct(results.bands.geo_test[i]?.observed_rate)}</td></tr>
            ))}
          </tbody>
        </table>
        <p>So roughly <b>3 in 4 areas marked high were still burning the next day</b>, against about 1 in 6 for low.</p>

        <h2>What we tested, and what we found</h2>
        <p>{results.study}.</p>
        <table>
          <thead><tr><th>2024 test set</th><th>Base rate</th><th>Seasonal pattern</th><th>Recent fire activity (used here)</th><th>+ weather</th></tr></thead>
          <tbody>
            {results.test_2024.map((r) => (
              <tr key={r.set}><td>{r.set}</td><td className="n">{f3(r.prevalence)}</td><td className="n">{f3(r.seasonal_B0)}</td>
                <td className="n">{f3(r.B1)}</td><td className="n">{f3(r.M2)}</td></tr>
            ))}
          </tbody>
        </table>
        <p className="small muted">Scores are PR-AUC (higher is better; the base rate is what guessing achieves).</p>
        <ul>
          <li><b>Recent fire activity beats the seasonal pattern</b> ({results.b1_vs_seasonal.map((b) => `${b.set}: +${b.difference.toFixed(3)}, 95% CI ${ci(b.ci95)}`).join("; ")}).</li>
          <li><b>{results.primary.conclusion}</b> ({results.primary.comparison}: {results.primary.difference >= 0 ? "+" : ""}{results.primary.difference.toFixed(4)}, 95% CI {ci(results.primary.ci95)}). So the map uses the simpler model.</li>
        </ul>

        <h2>Checks against other evidence</h2>
        <ul>{results.validation.map((v) => <li key={v.name}><b>{v.name}</b> ({v.independence}): {v.finding}</li>)}</ul>

        <h2>Limitations</h2>
        <ul>
          <li>"No fire detected" is not proof of no fire: clouds, smoke and timing between satellite passes hide fires.</li>
          <li>Fires and labels come from the same satellites. Checks against burn scars and ground reports support,
            but do not prove, that predictions reflect real fires.</li>
          <li>Near-real-time data is preliminary and can change for a few days.</li>
          <li>Satellite outages happen. On those days there are no predictions.</li>
          <li>State boundaries: geoBoundaries (DataMeet / Election Commission of India). They are not checked against the Survey of India map.</li>
        </ul>

        <h2>Data and model</h2>
        <ul>
          {meta.sources.map((s) => <li key={s}>{s}</li>)}
          <li>Model: {meta.model.id}, trained on {meta.model.trained_on}. Fingerprint <code>{meta.model.sha256.slice(0, 12)}</code>.</li>
          <li>Open source: <a href="https://github.com/codex0786/terrasentinel">github.com/codex0786/terrasentinel</a> (code, protocol, full reports).</li>
        </ul>
      </div>
    </div>
  );
}
