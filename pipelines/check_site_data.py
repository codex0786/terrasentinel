"""Data-quality guard: validate exported site data before it is published.

Exits non-zero (blocking deployment, so the previous good site stays live) if the data is stale, empty,
implausible, malformed, or missing a sensor. Warnings are reported but do not block.
Writes a machine-readable summary to <data>/health.json, which the site ships for monitoring.

    python pipelines/check_site_data.py [--data site/public/data] [--now 2026-10-15T12:00:00Z]
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path

from terrasentinel.config import REPO_ROOT, load_yaml

SCHEMA = "terrasentinel.site.v1"


def check(data: Path, now: datetime, cfg: dict) -> tuple[list[str], list[str], dict]:
    errors, warnings, facts = [], [], {}

    def load(name: str):
        p = data / name
        if not p.exists():
            errors.append(f"missing {name}")
            return None
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"{name} is not valid JSON ({exc})")
            return None

    meta, index = load("meta.json"), load("index.json")
    for name in ("states.json", "states.geojson", "results.json"):
        load(name)
    if meta is None or index is None:
        return errors, warnings, facts
    if meta.get("schema") != SCHEMA:
        errors.append(f"meta.schema is {meta.get('schema')!r}, expected {SCHEMA}")

    # freshness
    as_of = meta.get("data_as_of_utc")
    if not as_of:
        errors.append("no latest acquisition time (no detections at all?)")
    else:
        age = (now - datetime.fromisoformat(as_of)).total_seconds() / 3600
        facts["data_age_hours"] = round(age, 1)
        if age > cfg["max_data_age_hours"]:
            errors.append(f"satellite data is {age:.0f} h old (limit {cfg['max_data_age_hours']} h)")
    for s in cfg["required_sensors"]:
        if s not in meta.get("latest_acquisition_utc", {}):
            errors.append(f"sensor {s} has no data in this window")

    # days
    days = index.get("days", [])
    facts["days_exported"] = len(days)
    if len(days) < cfg["min_days_exported"]:
        errors.append(f"only {len(days)} days exported (need {cfg['min_days_exported']})")
    latest = meta.get("latest_day")
    if latest is None or not days or days[-1]["date"] != latest:
        errors.append("meta.latest_day does not match the last day in index.json")
    elif (now.date() - datetime.fromisoformat(latest).date()).days > cfg["max_latest_day_lag_days"]:
        errors.append(f"latest day {latest} is too old")
    for d in days:
        if not (data / "days" / f"{d['date']}.json").exists():
            errors.append(f"index lists {d['date']} but days/{d['date']}.json is missing")

    # plausibility of the latest completed day vs the recent baseline
    done = [d for d in days if d["outcomes_final"] and not d["unobserved"]]
    if len(done) >= 2:
        last, base = done[-1], done[-1 - cfg["baseline_days"]:-1]
        med = statistics.median(d["detections"] for d in base)
        facts.update(latest_complete_day=last["date"], latest_detections=last["detections"], baseline_median=med)
        if med >= cfg["min_baseline_detections"]:
            ratio = last["detections"] / med if med else float("inf")
            facts["detection_ratio"] = round(ratio, 3)
            if ratio < cfg["min_detection_ratio"]:
                errors.append(f"{last['date']}: {last['detections']} detections vs baseline median {med:.0f} "
                              f"(ratio {ratio:.2f} < {cfg['min_detection_ratio']}); possible data outage")
            elif ratio > cfg["max_detection_ratio"]:
                errors.append(f"{last['date']}: detections {ratio:.1f}x the baseline; possible duplicated data")
        else:
            warnings.append(f"baseline median {med:.0f} detections is below {cfg['min_baseline_detections']}; "
                            "ratio checks skipped")
    if meta.get("unobserved_days"):
        recent = [d for d in meta["unobserved_days"] if d >= (now.date() - timedelta(days=3)).isoformat()]
        if recent:
            warnings.append(f"sensor outage on recent day(s) {recent}: no predictions shown for them")

    # size of the first page load
    if latest and (data / "days" / f"{latest}.json").exists():
        gz = len(gzip.compress((data / "days" / f"{latest}.json").read_bytes())) / 1024
        facts["latest_day_gz_kb"] = round(gz, 1)
        if gz > cfg["max_today_gz_kb"]:
            errors.append(f"latest day file is {gz:.0f} KB gzipped (limit {cfg['max_today_gz_kb']})")
    return errors, warnings, facts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=REPO_ROOT / "site" / "public" / "data")
    p.add_argument("--now", type=lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")))
    args = p.parse_args()
    now = args.now or datetime.now(UTC)
    errors, warnings, facts = check(args.data, now, load_yaml("site_checks.yaml"))
    status = "fail" if errors else ("warn" if warnings else "ok")
    health = {"status": status, "checked_at_utc": now.isoformat(timespec="seconds"), "errors": errors,
              "warnings": warnings, **facts}
    if args.data.exists():
        (args.data / "health.json").write_text(json.dumps(health, indent=2))
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print(f"Site data check: {status.upper()} {json.dumps(facts)}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
