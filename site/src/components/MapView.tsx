import { useEffect, useRef } from "react";
import maplibregl, { GeoJSONSource, Map as MlMap } from "maplibre-gl";
import type { Day } from "../data";

interface Props {
  day: Day | null;
  shapes: GeoJSON.FeatureCollection | null;
  selectedState: string | null;
  selectedCell: string | null;
  showObs: boolean;
  showPred: boolean;
  onlyHigh: boolean;
  reveal: boolean;
  dark: boolean;
  onSelectCell: (id: string | null) => void;
  onSelectState: (name: string | null) => void;
}

const STYLE = (dark: boolean) => `https://tiles.openfreemap.org/styles/${dark ? "dark" : "positron"}`;
const INDIA: [[number, number], [number, number]] = [[68, 6.5], [97.5, 35.8]];

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function toPoints<T>(items: T[], ll: (x: T) => [number, number], props: (x: T) => Record<string, unknown>): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: items.map((x) => ({ type: "Feature", geometry: { type: "Point", coordinates: ll(x) }, properties: props(x) })),
  };
}

export default function MapView(p: Props) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const ready = useRef(false);
  const latest = useRef(p);
  latest.current = p;

  // create the map once per light/dark mode
  useEffect(() => {
    if (!box.current) return;
    const m = new maplibregl.Map({
      container: box.current, style: STYLE(p.dark), bounds: INDIA, fitBoundsOptions: { padding: 20 },
      attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.touchZoomRotate.disableRotation();
    map.current = m;
    if (window.location.search.includes("debug")) (window as unknown as { __tsMap?: MlMap }).__tsMap = m;
    m.on("load", () => {
      const empty: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
      m.addSource("states", { type: "geojson", data: latest.current.shapes ?? empty });
      m.addSource("detections", { type: "geojson", data: empty });
      m.addSource("cells", { type: "geojson", data: empty, promoteId: "id" });
      m.addLayer({ id: "states-fill", type: "fill", source: "states", paint: { "fill-color": "#000", "fill-opacity": 0 } });
      m.addLayer({ id: "states-line", type: "line", source: "states",
        paint: { "line-color": p.dark ? "#5b6170" : "#9aa0a6", "line-width": 0.7 } });
      m.addLayer({ id: "state-selected", type: "line", source: "states", filter: ["==", ["get", "name"], ""],
        paint: { "line-color": cssVar("--accent"), "line-width": 2.5 } });
      m.addLayer({ id: "detections", type: "circle", source: "detections", paint: {
        "circle-color": cssVar("--obs"), "circle-opacity": 0.75,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 1.6, 6, 3, 9, 5],
      } });
      m.addLayer({ id: "cells", type: "circle", source: "cells", paint: {
        "circle-color": ["match", ["get", "band"], "high", cssVar("--band-high"), "medium", cssVar("--band-medium"), cssVar("--band-low")],
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, ["match", ["get", "band"], "high", 4, "medium", 3, 2.4],
          7, ["match", ["get", "band"], "high", 9, "medium", 7, 5], 10, 18],
        "circle-opacity": ["case", ["==", ["get", "faded"], true], 0.25, 0.9],
        "circle-stroke-color": ["case", ["boolean", ["feature-state", "selected"], false], cssVar("--obs"),
          ["==", ["get", "band"], "high"], p.dark ? "#08306b" : "#ffffff", "rgba(0,0,0,0)"],
        "circle-stroke-width": ["case", ["boolean", ["feature-state", "selected"], false], 3,
          ["==", ["get", "band"], "high"], 1.5, 0],
      } });
      ready.current = true;
      sync();
      m.on("click", "cells", (e) => {
        const id = e.features?.[0]?.properties?.id as string | undefined;
        if (id) latest.current.onSelectCell(id);
      });
      m.on("click", (e) => {
        const hitCell = m.queryRenderedFeatures(e.point, { layers: ["cells"] }).length > 0;
        if (hitCell) return;
        const st = m.queryRenderedFeatures(e.point, { layers: ["states-fill"] })[0]?.properties?.name as string | undefined;
        latest.current.onSelectCell(null);
        latest.current.onSelectState(st ?? null);
      });
      for (const layer of ["cells", "states-fill"]) {
        m.on("mouseenter", layer, () => { m.getCanvas().style.cursor = "pointer"; });
        m.on("mouseleave", layer, () => { m.getCanvas().style.cursor = ""; });
      }
    });
    return () => { ready.current = false; m.remove(); map.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.dark]);

  function sync() {
    const m = map.current;
    if (!m || !ready.current) return;
    const { day, shapes, showObs, showPred, onlyHigh, reveal, selectedState } = latest.current;
    if (shapes) (m.getSource("states") as GeoJSONSource).setData(shapes);
    const dets = showObs && day ? day.detections : [];
    (m.getSource("detections") as GeoJSONSource).setData(toPoints(dets, (d) => [d.lon, d.lat], () => ({})));
    const cells = showPred && day ? day.cells.filter((c) => !onlyHigh || c.band === "high") : [];
    (m.getSource("cells") as GeoJSONSource).setData(toPoints(cells, (c) => [c.lon, c.lat],
      (c) => ({ id: c.id, band: c.band, faded: reveal && c.burnedAgain === 0 })));
    m.setFilter("state-selected", ["==", ["get", "name"], selectedState ?? ""]);
  }

  useEffect(sync, [p.day, p.shapes, p.showObs, p.showPred, p.onlyHigh, p.reveal, p.selectedState]);

  // highlight the selected cell
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    m.removeFeatureState({ source: "cells" });
    if (p.selectedCell) m.setFeatureState({ source: "cells", id: p.selectedCell }, { selected: true });
  }, [p.selectedCell, p.day]);

  // zoom to the selected state (or back to India)
  useEffect(() => {
    const m = map.current;
    if (!m || !p.shapes) return;
    const f = p.shapes.features.find((x) => x.properties?.name === p.selectedState);
    if (!f) { if (!p.selectedState) m.fitBounds(INDIA, { padding: 20, duration: 600 }); return; }
    const b = new maplibregl.LngLatBounds();
    const walk = (c: unknown): void => {
      if (Array.isArray(c) && typeof c[0] === "number") b.extend(c as [number, number]);
      else if (Array.isArray(c)) c.forEach(walk);
    };
    walk((f.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon).coordinates);
    m.fitBounds(b, { padding: 40, duration: 700, maxZoom: 8 });
  }, [p.selectedState, p.shapes]);

  return <div ref={box} className="map" role="region" aria-label="Map of fire detections and predictions" />;
}
