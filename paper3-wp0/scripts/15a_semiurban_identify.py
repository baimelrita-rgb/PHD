"""WP2 step 1: identify Sherlock 02-Semiurban's additions to SimBench 1-MV-semiurb--2-sw.

Found in the data:
  * The IEC 104 data-point map groups points by RTU; 56 RTU groups each hold one MV bus, one
    new bus (122..177), one new transformer (2..57), two new switches and some elements.
  * The power balance of every new bus (recorded bus P versus element P over many
    snapshots) identifies the elements on it: always one sgen and one storage unit.
  * Transformer rating from recorded loading (S_hv / (V_hv x loading)), then losses fitted as
    in 01-Basic: P_loss = pfe + vkr Sn (S/Sn)^2, Q_loss = q0 + vk_x Sn (S/Sn)^2.
Writes rules/semiurban_structure.json and reports/semiurban_identify.md. Data only."""
import collections
import itertools
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C

from p3 import semiurban_model as SU
from p3 import sherlock_io as S


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n", type=int, default=300, help="train snapshots used")
    ap.set_defaults(grid="semiurban")
    a = ap.parse_args()
    ROOT = S.root(a.grid)
    OUT = SU.RULES / SU.SPECS[a.grid]["struct"]
    base = SU.simbench_base(a.grid)
    NB0, NSW0 = len(base.bus), len(base.switch)
    dpm = json.loads((ROOT / "raw" / "train" / "data-point-map.json").read_text())
    groups = collections.defaultdict(set)
    for ioa, d in dpm.items():
        groups[ioa.split(".")[0]].add(d["element"])
    z = zipfile.ZipFile(ROOT / "raw" / "train" / "physical.zip")
    names = sorted(x for x in z.namelist() if x.startswith("physical/") and x.endswith(".json"))
    pick = np.random.default_rng(a.seed).choice(len(names), a.n, replace=False)
    snaps = [json.loads(z.read(names[k]))["values"] for k in pick]
    P = lambda key: np.array([s[key] for s in snaps]) / 1e6
    sign = {"sgen": -1.0, "load": 1.0, "storage": 1.0}
    structs, max_err = [], 0.0
    for g, els in groups.items():
        nb = [int(e.split(".")[1]) for e in els if e.startswith("bus.") and int(e.split(".")[1]) >= NB0]
        if not nb:
            continue
        b = nb[0]
        mv = [int(e.split(".")[1]) for e in els if e.startswith("bus.") and int(e.split(".")[1]) < NB0]
        tr = [int(e.split(".")[1]) for e in els if e.startswith("trafo.")]
        sw = sorted(int(e.split(".")[1]) for e in els if e.startswith("switch.") and int(e.split(".")[1]) >= NSW0)
        cand = [e for e in els if e.split(".")[0] in sign]
        bp = P(f"bus.{b}.MEASUREMENT.active_power")
        best = (np.inf, None)
        for r in range(1, len(cand) + 1):
            for sub in itertools.combinations(cand, r):
                s = sum(sign[e.split(".")[0]] * P(f"{e}.MEASUREMENT.active_power") for e in sub)
                err = float(np.abs(s - bp).max())
                if err < best[0]:
                    best = (err, sub)
        max_err = max(max_err, best[0])
        assert len(mv) == 1 and len(tr) == 1 and len(sw) == 2, (g, els)
        t = tr[0]
        # transformer: which side is the MV bus? compare recorded hv voltage with the two buses
        vh = np.array([s[f"trafo.{t}.MEASUREMENT.voltage_hv"] for s in snaps])
        e_mv = np.abs(vh - np.array([s[f"bus.{mv[0]}.MEASUREMENT.voltage"] for s in snaps])).max()
        e_nb = np.abs(vh - np.array([s[f"bus.{b}.MEASUREMENT.voltage"] for s in snaps])).max()
        structs.append({"new_bus": b, "mv_bus": mv[0], "trafo": t, "switches": sw,
                        "hv_is_mv": bool(e_mv < e_nb), "hv_match_err": float(min(e_mv, e_nb)),
                        "elements": sorted(best[1]), "balance_err_mw": best[0]})
    structs.sort(key=lambda s: s["trafo"])

    def fit(t):
        Ph, Qh = P(f"trafo.{t}.MEASUREMENT.active_power_hv"), P(f"trafo.{t}.MEASUREMENT.reactive_power_hv")
        Vh = np.array([s[f"trafo.{t}.MEASUREMENT.voltage_hv"] for s in snaps])
        ld = np.array([s[f"trafo.{t}.MEASUREMENT.loading"] for s in snaps])
        S_ = np.hypot(Ph, Qh) / Vh
        pl, ql = P(f"trafo.{t}.MEASUREMENT.active_power_loss"), P(f"trafo.{t}.MEASUREMENT.reactive_power_loss")
        fin = np.isfinite(S_) & np.isfinite(ld) & np.isfinite(pl) & np.isfinite(ql)
        ok = fin & (ld > 1)
        if ok.sum() < 10:
            return {"sn_mva": float("nan"), "vkr_percent": float("nan"), "vk_percent": float("nan"), "pfe_kw": float("nan"),
                    "i0_percent": float("nan"), "loss_resid_kw": float("nan"), "loading_range": [float(np.nanmin(ld)), float(np.nanmax(ld))],
                    "n_ok": int(ok.sum())}
        sn = float(np.median(S_[ok] / (ld[ok] / 100)))
        x = S_[fin] ** 2 / sn
        A = np.c_[np.ones_like(x), x]
        cp = np.linalg.lstsq(A, pl[fin], rcond=None)[0]
        cq = np.linalg.lstsq(A, ql[fin], rcond=None)[0]
        resid = float(np.abs(pl[fin] - A @ cp).max())
        vkr, vkx = 100 * cp[1], 100 * cq[1]
        return {"sn_mva": sn, "vkr_percent": float(vkr), "vk_percent": float(np.hypot(vkr, vkx)),
                "pfe_kw": float(1e3 * cp[0]), "i0_percent": float(100 * np.hypot(cp[0], cq[0]) / sn),
                "loss_resid_kw": 1e3 * resid, "loading_range": [float(np.nanmin(ld)), float(np.nanmax(ld))], "n_ok": int(ok.sum())}

    n_tr = len({k.split(".")[1] for k in snaps[0] if k.startswith("trafo.")})
    tparams = {t: fit(t) for t in range(n_tr)}
    OUT.write_text(json.dumps({"source": "scripts/15a_semiurban_identify.py", "structures": structs,
                               "trafo": {str(k): v for k, v in tparams.items()}}, indent=2))
    body = f"# Sherlock {a.grid}: additions to SimBench {SU.SPECS[a.grid]['code']} identified from data\n\n"
    body += C.md_table(["quantity", "value"], [
        ["RTU groups with a new bus", len(structs)],
        ["elements on each new bus", ", ".join(f"{k} {v}" for k, v in collections.Counter(tuple(sorted(e.split('.')[0] for e in s["elements"])) for s in structs).items())],
        ["max power balance error over all new buses and snapshots, MW", f"{max_err:.2e}"],
        ["transformer HV voltage closer to the MV bus than to the new bus", f"{sum(s['hv_is_mv'] for s in structs)} of {len(structs)} (the rest are within measurement noise; the model puts HV on the MV bus, the physical 20 kV side)"],
        ["max HV voltage match error, pu", f"{max(s['hv_match_err'] for s in structs):.2e}"],
        ["snapshots used", f"{a.n} (seed {a.seed})"],
    ])
    rows = []
    for t in sorted({0, 1, 2, 3, n_tr // 2, n_tr - 1}):
        p = tparams[t]
        rows.append([t, f"{p['sn_mva']:.3f}", f"{p['vk_percent']:.3f}", f"{p['vkr_percent']:.3f}", f"{p['pfe_kw']:.2f}",
                     f"{p['i0_percent']:.3f}", f"{p['loss_resid_kw']:.3f}", f"{p['loading_range'][0]:.1f} to {p['loading_range'][1]:.1f}"])
    body += f"\nFitted transformer parameters (sample; all {n_tr} in `rules/{OUT.name}`):\n\n"
    body += C.md_table(["trafo", "Sn MVA", "vk %", "vkr %", "pfe kW", "i0 %", "max P-loss residual kW", "loading % range"], rows)
    sn_new = np.array([tparams[s_["trafo"]]["sn_mva"] for s_ in structs])
    body += (f"\nNew transformers 2..57: Sn from {np.nanmin(sn_new):.3f} to {np.nanmax(sn_new):.3f} MVA. SimBench's own "
             "transformers 0 and 1 are 40 MVA, vk 16.2 %, vkr 0.34 %, pfe 18 kW, i0 0.05 %.\n")
    C.write_report("semiurban_identify.md" if a.grid == "semiurban" else f"{a.grid}_identify.md", body)
    print(f"structures {len(structs)}, balance err {max_err:.2e}")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
