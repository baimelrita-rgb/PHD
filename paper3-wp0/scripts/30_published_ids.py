"""Improvement B1: published IDSs on identical data.

Runs SIMPLE (its five components MinMax, Histogram, SteadyTime, Exists, DecimalPlaces, combined
with the framework's Any combiner) and GeCo from the dataset group's open IPAL IDS framework
(github.com/fkie-cad/ipal_ids_framework, third-party code, kept outside this repository) with the
framework's default parameters, trained on the same training file and run on the same test file as
our methods, without any measurement filtering. Features: every numeric field of the IPAL state.
Scored with the dataset paper's metrics (as scripts/24) and with our false alarms per benign record."""
import gzip
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import sherlock_io as S

FW = Path(os.environ.get("IPAL_IDS", "/home/user/ext/ipal_ids_framework"))
PY = Path(os.environ.get("IPAL_PY", "/home/user/ext/ipalenv/bin/python"))


def numeric_keys(state_file):
    with gzip.open(state_file, "rt") as f:
        st = json.loads(f.readline())["state"]
    return sorted(k for k, v in st.items() if isinstance(v, (int, float)) and not isinstance(v, bool)) , \
        sorted(k for k, v in st.items() if isinstance(v, bool))


def configs(num, boo, work):
    feats = [f"state;{k}" for k in num + boo]
    base = lambda t, **kw: {"_type": t, "model-file": str(work / f"{t}.model"), **kw}
    simple = {"MinMax": base("MinMax", features=feats, preprocessors=[], trainon=1.0, **{"save-training": None, "allow-none": True, "threshold": 1.0, "discrete_threshold": 10}),
              "Histogram": base("Histogram", features=feats, preprocessors=[], trainon=1.0, **{"save-training": None, "allow-none": True, "window_size": 100, "threshold": 1.0, "discrete_threshold": 10}),
              "SteadyTime": base("SteadyTime", features=feats, preprocessors=[], trainon=1.0, **{"save-training": None, "allow-none": True, "threshold": 1.0, "discrete_threshold": 10, "adjust": True}),
              "ExistsIDS": base("ExistsIDS", exclude=[], threshold=10),
              "DecimalPlaces": base("DecimalPlaces")}
    geco = {"GeCo": base("GeCo", ignore=[f"state;{k}" for k in boo], max_formel_length=3, threshold_factor=1.1, cusum_factor=2, cpus=4, refit=False, resume=False)}
    return {"SIMPLE": simple, "GeCo": geco}


def run(name, cfg, train, test, work, timeout):
    cf = work / f"{name}.config"; cf.write_text(json.dumps(cfg, indent=1))
    comb = work / "any.combiner"; comb.write_text(json.dumps({"_type": "Any", "model-file": str(work / "any.model")}))
    out = work / f"{name}.output.gz"
    cmd = [str(PY), "ipal-iids", "--config", str(cf), "--train.state", str(train), "--live.state", str(test), "--output", str(out), "--log", "WARNING"]
    if name == "SIMPLE":
        cmd += ["--combiner.config", str(comb)]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=FW, capture_output=True, text=True, timeout=timeout)
        ok = p.returncode == 0
        err = p.stderr[-600:]
    except subprocess.TimeoutExpired:
        ok, err = False, f"timeout after {timeout} s"
    return out if ok else None, time.time() - t0, err


def alarms(out):
    T, A = [], []
    with gzip.open(out, "rt") as f:
        for ln in f:
            m = json.loads(ln)
            T.append(m["timestamp"]); A.append(bool(m.get("ids", False)))
    return np.array(T), np.array(A)


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--ids", default="SIMPLE,GeCo")
    ap.add_argument("--timeout", type=int, default=7200)
    ap.set_defaults(grid="sherlock")
    a = C.init(ap.parse_args())
    import importlib.util
    sp = importlib.util.spec_from_file_location("s24", Path(__file__).with_name("24_sherlock_metrics.py"))
    s24 = importlib.util.module_from_spec(sp); sp.loader.exec_module(s24)
    root = S.root()
    train = sorted(root.glob("train.*.state.gz"))[0]; test = sorted(root.glob("test.*.state.gz"))[0]
    work = C.INTERIM.parent / "ipal_runs" / C.suffixed("run").replace(".", "_"); work.mkdir(parents=True, exist_ok=True)
    num, boo = numeric_keys(train)
    cfgs = configs(num, boo, work)
    ev = S.load_events(root, "test")
    rows = []
    for name in a.ids.split(","):
        out, sec, err = run(name, cfgs[name], train, test, work, a.timeout)
        if out is None:
            rows.append([name, "failed", "", "", "", f"{sec:.0f}", err.replace("\n", " ")[:200]]); print(rows[-1]); continue
        T, A = alarms(out)
        det, fa, ttd = s24.score(T, A, ev)
        near = np.zeros(len(T), bool)
        proc = [e for e in ev if "benign" not in e["id"]]
        for e in proc:
            near |= (T >= e["start"] - 60) & (T <= e.get("recovery", e["end"]) + 60)
        rate = A[~near].mean()
        pa = [e for e in proc if e["description"] != "arp-spoof:arp-spoof-dos"]
        pdet = sum(bool(A[(T >= e["start"]) & (T <= e.get("recovery", e["end"]))].any()) for e in pa)
        np.savez_compressed(C.interim(f"published_{name}.npz"), t=T, alarm=A)
        rows.append([name, det, fa, ttd, f"{rate:.5f} ({pdet}/{len(pa)} process attacks)", f"{sec:.0f}", ""])
        print(rows[-1])
    body = "# Improvement B1: published IDSs on identical data\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    body += f"Training file `{train.name}`, test file `{test.name}`, {len(num)} numeric and {len(boo)} Boolean state fields.\n\n"
    body += C.md_table(["IDS", "detected attacks (dataset metric)", "false alarms (at benign events)", "mean TTD s",
                        "false alarms per benign record (ours)", "wall s", "note"], rows)
    C.write_report("published_ids.md", body)


if __name__ == "__main__":
    main()
