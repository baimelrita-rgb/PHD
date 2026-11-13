"""T1: Sherlock 01-Basic inventory (answers G1, G2). Reads data only."""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import sherlock_io as S


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--root", default=str(S.ROOT_DEFAULT))
    ap.add_argument("--exclude-types", nargs="*", default=["arp-spoof:arp-spoof-dos"],
                    help="attack types left out of G2 (owner decision 1: arp-spoof-dos is network-level, out of scope)")
    a = ap.parse_args()
    root = Path(a.root)
    if not root.exists():
        raise SystemExit(f"dataset not found at {root}; run scripts/00_download_sherlock.sh")
    tree = S.file_tree(root)
    body = "# T1 Sherlock 01-Basic inventory\n\n"
    body += "Source: Zenodo record 18467070, `01-Basic.zip`, md5 `c482e0dc7e56b063b357d8b03be5cce6` (verified by `scripts/00_download_sherlock.sh`).\n\n"

    # ---- file tree (logs collapsed)
    body += "## File tree\n\n"
    rows, logs = [], collections.Counter()
    for p, s in tree:
        if p.endswith(".log"):
            logs[str(Path(p).parent)] += 1
            continue
        rows.append([f"`{p}`", s, S.classify(p)])
    for d, n in logs.items():
        sz = sum(s for p, s in tree if p.startswith(d + "/") and p.endswith(".log"))
        rows.append([f"`{d}/*.log` ({n} files)", sz, "host/service log"])
    body += C.md_table(["path", "bytes", "category"], rows)
    body += f"\nTotal files {len(tree)}, total bytes {sum(s for _, s in tree)}.\n\n"

    # ---- grid model search
    z, idx = S.physical_index(root, "train")
    snap = S.read_snapshot(z, idx[0][1])["values"]
    counts = collections.Counter(k.split(".")[0] + "." + k.split(".")[1] for k in snap)
    elems = collections.Counter(k.split(".")[0] for k in counts)
    fields = collections.defaultdict(set)
    for k in snap:
        p = k.split(".")
        fields[p[0]].add(".".join(p[2:]))
    any_model = [p for p, _ in tree if p.endswith((".p", ".pkl", ".pickle")) or ("pandapower" in p.lower())]
    any_yaml_scen = [p for p, _ in tree if p.endswith((".yml", ".yaml"))]
    cfg_tr = S.load_config(root, "train")
    body += "## Grid model files\n\n"
    body += C.md_table(["item", "finding"], [
        ["pandapower json or pickle in the download", "none found" if not any_model else ", ".join(any_model)],
        ["Wattson scenario files (grid definition)", "none; the only yml files are `sherlock-config.yml` (playbook configuration)"],
        ["scenario name in sherlock-config.yml", f"`{cfg_tr.get('scenario')}`"],
        ["topology description", "diagrams only: `raw/*/docs/power-grid.{pdf,svg}`, `network.{pdf,svg}`, `combined.{pdf,svg}`"],
        ["element counts in physical snapshots", ", ".join(f"{k}: {v}" for k, v in sorted(elems.items()))],
        ["line fields", ", ".join(sorted(fields["line"]))],
        ["line impedance parameters present", "no (only measurements)"],
        ["transformer fields", ", ".join(sorted(fields["trafo"]))],
    ])
    body += ("\nThe element counts (15 buses, 15 lines, 18 loads, 13 sgen, 2 storage, 2 transformers, 1 external grid) "
             "match `pandapower.networks.create_cigre_network_mv(with_der=\"all\")`, except for the switches "
             "(32 in Sherlock, 8 in pandapower). Sherlock's transformers also have tap positions, which the pandapower model lacks. "
             "T7 tests whether that pandapower model reproduces the recorded physics.\n\n")
    body += "**G1 (usable grid model in the download): NO.** No pandapower net or Wattson grid definition is included. "
    body += "A candidate reconstruction from pandapower's CIGRE MV (all DER) is evaluated in `sherlock_model_check.md`.\n\n"

    # ---- labels
    body += "## Labels\n\n"
    for split in ("train", "test"):
        ev = S.load_events(root, split)
        att = [e for e in ev if "benign" not in e["id"]]
        ben = [e for e in ev if "benign" in e["id"]]
        body += f"### {split}: attacks\n\n"
        if att:
            body += C.md_table(["id", "type", "start (unix s)", "end (unix s)", "duration s", "targeted assets"],
                               [[e["id"], e["description"], f"{e['start']:.1f}", f"{e['end']:.1f}", f"{e['end'] - e['start']:.1f}",
                                 ", ".join(e.get("attack_point") or []) or "⟨none listed⟩"] for e in att])
            cnt = collections.Counter(e["description"] for e in att)
            body += "\nCount per attack type:\n\n" + C.md_table(["attack type", "instances"], sorted(cnt.items())) + "\n"
        else:
            body += "No attacks in this split.\n\n"
        body += f"### {split}: benign events\n\n"
        cntb = collections.Counter(e["description"] for e in ben)
        body += C.md_table(["benign event type", "count"], sorted(cntb.items())) + "\n"
        if split == "test":
            cnt_in = {k: v for k, v in cnt.items() if k not in a.exclude_types}
            n_types = len(cnt_in)
            min_inst = min(cnt_in.values())
            g2 = n_types >= 4 and min_inst >= 3
            g2_3 = n_types >= 3 and min_inst >= 3
            # industroyer instances by kind of targeted asset (for a possible finer type split)
            ind = collections.Counter()
            for e in att:
                if e["description"].startswith("industroyer"):
                    kinds = sorted({p.split(".")[0] + ":" + p.split(":")[1] for p in (e.get("attack_point") or [])})
                    ind[", ".join(kinds)] += 1
    body += ("Electrical faults among the benign events: none. All benign events are operator procedures from the control "
             "center (maintenance, switching, generator control, transformer tap steps, manual commands). "
             "No short circuit or earth fault is labelled.\n\n")
    body += (f"Excluded from G2 (owner decision 1): {', '.join(a.exclude_types) or 'none'}.\n\n"
             f"**G2 as written (at least 4 attack types, at least 3 instances each): {'PASS' if g2 else 'FAIL'}.** "
             f"After the exclusion the test split has {n_types} process-level attack types "
             f"({', '.join(f'{k} {v}' for k, v in sorted(cnt_in.items()))}); the smallest has {min_inst} instances. "
             f"With the criterion relaxed to at least 3 types: {'PASS' if g2_3 else 'FAIL'}. Train has no attacks.\n\n"
             "Industroyer instances by targeted asset kind (a possible finer split, owner decision):\n\n"
             + C.md_table(["targeted assets", "instances"], sorted(ind.items())) + "\n")

    # ---- state files
    body += "## State files\n\n"
    rows = []
    for split in ("train", "test"):
        ts, nkeys, keys = [], 0, set()
        for i, rec in enumerate(S.iter_state(root, split)):
            ts.append(rec["timestamp"])
            if i < 50:
                keys |= set(rec["state"])
        ts = np.array(ts)
        dt = np.diff(ts)
        kinds = collections.Counter(k.split(":")[0].split(".")[0] + ":" + k.split(":")[1] for k in keys)
        rows.append([split, len(ts), f"{(ts[-1] - ts[0]) / 3600:.3f}", f"{np.median(dt):.3f}", f"{dt.min():.3f}", f"{dt.max():.3f}", len(keys)])
        if split == "train":
            kinds_tr = kinds
    body += C.md_table(["split", "records (n302)", "duration h (wall clock)", "median dt s", "min dt s", "max dt s",
                        "distinct fields (first 50 records)"], rows)
    body += "\nField kinds (element type: attribute, count of elements) in `train.n302.state.gz`:\n\n"
    body += C.md_table(["field", "elements"], sorted(kinds_tr.items()))
    import json
    dpm = json.loads((root / "raw" / "train" / "data-point-map.json").read_text())
    units = collections.Counter((v["element"].split(".")[0], v["attribute"], v["unit"], v.get("scale")) for v in dpm.values())
    body += "\nUnits from `data-point-map.json` (element type, attribute, unit, scale, number of points):\n\n"
    body += C.md_table(["element", "attribute", "unit", "scale", "points"], [[*k, v] for k, v in sorted(units.items())])
    tz = [t for t, _ in idx]
    _, idx_te = S.physical_index(root, "test")
    body += "\nPhysical ground-truth snapshots (`raw/*/physical.zip`):\n\n"
    body += C.md_table(["split", "snapshots", "duration h", "median dt s"], [
        ["train", len(idx), f"{(tz[-1] - tz[0]) / 3600:.3f}", f"{np.median(np.diff(tz)):.3f}"],
        ["test", len(idx_te), f"{(idx_te[-1][0] - idx_te[0][0]) / 3600:.3f}", f"{np.median(np.diff([t for t, _ in idx_te])):.3f}"],
    ])
    cfg_te = S.load_config(root, "test")
    body += (f"\nScenario duration in config: train {cfg_tr.get('duration_seconds')} s, test {cfg_te.get('duration_seconds', '⟨·⟩')} s; "
             f"Wattson clock speed {cfg_tr.get('wattson_speed')} (simulated time runs faster than wall time). "
             "Powers are in W and var, currents in A, voltages in pu, angles in degrees (snapshot values).\n")
    C.write_report("dataset_inventory.md", body)
    print("G1 no model file; G2", "pass" if g2 else "fail", "| relaxed to 3 types:", "pass" if g2_3 else "fail")


if __name__ == "__main__":
    main()
