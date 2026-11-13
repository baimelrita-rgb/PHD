"""Sherlock 01-Basic inventory and loaders. Everything in the archive is treated as
data: JSON/JSONL/gz are parsed, nothing from the dataset is executed or imported
(ipal/rules.py is only listed, never run)."""
from __future__ import annotations

import gzip
import json
import re
import zipfile
from pathlib import Path

ROOT_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "raw" / "01-Basic" / "01-Basic"
ROOT_SEMI = Path(__file__).resolve().parents[2] / "data" / "raw" / "02-Semiurban" / "02-Semiurban"
ROOT_RURAL = Path(__file__).resolve().parents[2] / "data" / "raw" / "03-Rural" / "03-Rural"
ROOTS = {"semiurban": ROOT_SEMI, "rural": ROOT_RURAL}


def root(name=None) -> Path:
    """Dataset root for a grid (default: the active grid): 02-Semiurban, 03-Rural, else 01-Basic."""
    if name is None:
        from . import envelope as E
        name = E.grid().name
    return ROOTS.get(name, ROOT_DEFAULT)


def file_tree(root: Path):
    return sorted((str(p.relative_to(root)), p.stat().st_size) for p in root.rglob("*") if p.is_file())


def classify(path: str) -> str:
    p = path.lower()
    if p.endswith((".pcap", ".pcapng")):
        return "network capture"
    if "physical.zip" in p:
        return "physical ground-truth snapshots (zip of power_grid_*.json)"
    if p.endswith(".state.gz"):
        return "IPAL state file"
    if p.startswith("ipal/") and p.endswith("events.json"):
        return "labels (IPAL events)"
    if p.endswith("initial_state.json"):
        return "IPAL initial state"
    if p.endswith("rules.py"):
        return "IPAL state-extraction rules (code; listed, not executed)"
    if p.endswith("events.jsonl"):
        return "simulator event log (labels source)"
    if p.endswith("data-point-map.json"):
        return "IEC 104 data point map"
    if p.endswith("sherlock-config.yml"):
        return "scenario configuration"
    if "/docs/" in p:
        return "documentation (diagram)"
    if p.endswith(".log"):
        return "host/service log"
    if "control-center.zip" in p:
        return "control-center notifications (zip)"
    return "other"


def load_events(root: Path, split: str):
    return json.loads((root / "ipal" / split / "events.json").read_text())


def load_config(root: Path, split: str):
    # files are named .yml but contain JSON; parse with yaml (safe loader) which accepts both
    import yaml
    return yaml.safe_load((root / "raw" / split / "sherlock-config.yml").read_text())


def iter_state(root: Path, split: str, vantage: str | None = None):
    if vantage is None:
        files = sorted(root.glob(f"{split}.*.state.gz"))
        assert len(files) == 1, files
        path = files[0]
    else:
        path = root / f"{split}.{vantage}.state.gz"
    with gzip.open(path, "rt") as f:
        for line in f:
            yield json.loads(line)


_TS = re.compile(r"TS(\d+)-(\d+)\.json$")


def physical_index(root: Path, split: str):
    """List of (timestamp, member name) of the ground-truth snapshots, sorted."""
    z = zipfile.ZipFile(root / "raw" / split / "physical.zip")
    out = []
    for n in z.namelist():
        if n.startswith("physical/") and n.endswith(".json"):
            m = _TS.search(n)
            out.append((float(f"{m.group(1)}.{m.group(2)}"), n))
    out.sort()
    return z, out


def read_snapshot(z: zipfile.ZipFile, member: str) -> dict:
    return json.loads(z.read(member))
