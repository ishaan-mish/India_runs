#!/usr/bin/env python3
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "outputs" / "smoke_top10.csv"
subprocess.run([sys.executable, str(ROOT / "ranker.py"), "--candidates", str(ROOT / "data" / "sample_candidates.json"), "--output", str(out), "--dashboard-json", str(ROOT / "outputs" / "smoke_payload.json"), "--top", "10"], check=True, cwd=ROOT)
with out.open("r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
assert len(rows) == 10
assert [int(r["rank"]) for r in rows] == list(range(1,11))
scores = [float(r["score"]) for r in rows]
assert all(scores[i] >= scores[i+1] for i in range(len(scores)-1))
print("smoke test passed", out)
