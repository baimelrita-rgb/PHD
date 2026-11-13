"""WP2 step 2: does the reconstructed 02-Semiurban grid reproduce the recorded physics?
Same check as T7 for 01-Basic: inputs from each ground-truth snapshot (external grid voltage,
all load / sgen / storage P and Q and connection states, all 360 switch states, taps), one AC
power flow, computed minus recorded for bus voltages, line P and transformer P."""
import json
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandapower as pp

from p3 import common as C
from p3 import semiurban_model as SU

from p3 import sherlock_io as S


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--split", default="train")
    ap.set_defaults(grid="semiurban")
    a = ap.parse_args()
    ROOT = S.root(a.grid)
    if not (ROOT / "raw" / a.split).exists():
        raise SystemExit(f"no {a.split} split for {a.grid}")
    t0 = time.time()
    z = zipfile.ZipFile(ROOT / "raw" / a.split / "physical.zip")
    names = sorted(x for x in z.namelist() if x.startswith("physical/") and x.endswith(".json"))
    pick = np.random.default_rng(a.seed + 1).choice(len(names), a.n, replace=False)
    net = SU.base_net(a.grid)
    ev, ep, et, nf, nonconv = [], [], [], [], 0
    for k in pick:
        v = json.loads(z.read(names[k]))["values"]
        SU.build(v, net, a.grid)
        try:
            pp.runpp(net)
        except pp.LoadflowNotConverged:
            nonconv += 1
            continue
        rec_v = np.array([v[f"bus.{b}.MEASUREMENT.voltage"] for b in net.bus.index])
        ok = np.isfinite(net.res_bus.vm_pu.values)
        ev.append(np.abs(net.res_bus.vm_pu.values[ok] - rec_v[ok]))
        lin = net.line.in_service.values & np.isfinite(net.res_line.p_from_mw.values)
        ep.append(np.abs(net.res_line.p_from_mw.values[lin] - np.array([v[f"line.{l}.MEASUREMENT.active_power_from"] for l in net.line.index])[lin] / 1e6))
        et.append(np.abs(net.res_trafo.p_hv_mw.values - np.array([v[f"trafo.{t}.MEASUREMENT.active_power_hv"] for t in net.trafo.index]) / 1e6))
        live = [l for l in net.line.index if v[f"line.{l}.MEASUREMENT.current_from"] > 0.5 and v[f"line.{l}.MEASUREMENT.current_to"] > 0.5]
        nf.append(max(abs(v[f"line.{l}.MEASUREMENT.voltage_from"] - v[f"bus.{int(net.line.from_bus.at[l])}.MEASUREMENT.voltage"]) for l in live))
    ev, ep, et = (np.concatenate(x) for x in (ev, ep, et))
    p = SU.new_trafo_params(a.grid)
    body = f"# Sherlock {a.grid}: model check ({a.split})\n\n"
    body += (f"Reconstruction: SimBench {SU.SPECS[a.grid]['code']} plus the {len(SU.structure(a.grid)['structures'])} identified bus / transformer / switch / DER and "
             f"storage groups (`semiurban_identify.md`); new transformers: Sn {p['sn_mva']:.3f} MVA, vk {p['vk_percent']:.3f} %, "
             f"vkr {p['vkr_percent']:.3f} %, pfe {p['pfe_kw']:.2f} kW, i0 {p['i0_percent']:.3f} % (median fit). Inputs from each "
             f"ground-truth snapshot; one AC power flow each. Wall time {time.time() - t0:.0f} s.\n\n")
    body += C.md_table(["quantity", "value"], [
        ["snapshots compared (seeded random)", f"{len(pick) - nonconv} of {len(pick)} (not converged {nonconv})"],
        ["measurement noise floor: max |line voltage_from - bus voltage| over energised lines (both end currents above 0.5 A), pu", f"{max(nf):.2e}"],
    ])
    body += "\n" + C.md_table(["quantity", "unit", "mean abs", "95th pct", "max abs"], [
        ["bus voltage magnitude (178 buses)", "pu", f"{ev.mean():.2e}", f"{np.percentile(ev, 95):.2e}", f"{ev.max():.2e}"],
        ["line active power, from end", "MW", f"{ep.mean():.2e}", f"{np.percentile(ep, 95):.2e}", f"{ep.max():.2e}"],
        ["transformer active power, HV side", "MW", f"{et.mean():.2e}", f"{np.percentile(et, 95):.2e}", f"{et.max():.2e}"],
    ])
    C.write_report(f"semiurban_model_check_{a.split}.md" if a.grid == "semiurban" else f"{a.grid}_model_check_{a.split}.md", body)
    print(f"vm mean {ev.mean():.2e} max {ev.max():.2e}; p max {ep.max():.2e}; trafo max {et.max():.2e}; noise {max(nf):.2e}; nonconv {nonconv}")


if __name__ == "__main__":
    main()
