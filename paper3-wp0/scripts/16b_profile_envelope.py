"""WP3: a priori benign envelope from SimBench planning profiles (no recorded data used).

For grids without a train day (03-Rural): load P and Q bounds are the min / max of each load's
SimBench profile multiplier, widened by --margin (0.05, justified on 02-Semiurban where monitored
train loads exceed their profile range by at most 0.046); sgen [0, 1] of rated, storage [-1, 1]
of nominal (physical ranges); the topology list holds only the topology of the first test record
(the initial configuration); other topologies are certified on demand. Coverage of benign test
records is measured afterwards (labels used only to exclude attack windows from that count)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import semiurban_model as SU
from p3 import sherlock_io as S


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--margin", type=float, default=0.05)
    ap.add_argument("--noise-tol", type=float, default=1e-3)
    ap.add_argument("--step", type=int, default=10)
    ap.set_defaults(grid="rural")
    a = ap.parse_args()
    base = SU.simbench_base(a.grid)
    lp = base.profiles["load"]
    lo = np.array([float(lp[f"{p}_pload"].min()) for p in base.load.profile]) - a.margin
    hi = np.array([float(lp[f"{p}_pload"].max()) for p in base.load.profile]) + a.margin
    # reactive power: Sherlock's load Q does not follow SimBench's qload profiles (on 02-Semiurban recorded Q / nominal
    # spans beyond the profile range), so the bounds are transferred from the 02-Semiurban train recording instead:
    # overall min / max of Q / nominal Q over its loads, widened by the margin (no Rural data used)
    semi = json.loads(E._sb_env_path("semiurban").read_text())
    sq = np.array(semi["load_q_bounds"])          # already widened by Semiurban's own 0.01 margin
    q_lo_t, q_hi_t = float(sq[:, 0].min()) + 0.01, float(sq[:, 1].max()) - 0.01
    qlo = np.full(len(base.load), q_lo_t - a.margin)
    qhi = np.full(len(base.load), q_hi_t + a.margin)
    net = SU.base_net(a.grid)
    root = S.root(a.grid)
    first = next(iter(S.iter_state(root, "test")))["state"]
    E.use_grid(a.grid) if E._sb_env_path(a.grid).exists() else None
    # initial topology: lines with an open switch in the first record (unmonitored switches at their fixed state)
    z, idx = S.physical_index(root, "test")
    snap0 = S.read_snapshot(z, idx[0][1])["values"]
    fixed = {int(k.split(".")[1]): bool(v) for k, v in snap0.items() if k.startswith("switch.") and k.endswith("MEASUREMENT.is_closed")}
    lsw = {}
    for s_ in net.switch.index:
        if net.switch.et.at[s_] == "l":
            lsw.setdefault(int(net.switch.element.at[s_]), []).append(int(s_))
    closed = lambda st, s_: bool(st.get(f"switch.{s_}:is_closed", fixed[s_]))
    topo0 = sorted(l for l, ss in lsw.items() if any(not closed(first, s_) for s_ in ss))
    env = {"source": f"scripts/16b_profile_envelope.py: SimBench {SU.SPECS[a.grid]['code']} profiles, margin {a.margin}",
           "load_q": "free",
           "load": [[float(x), float(y)] for x, y in zip(lo, hi)],
           "sgen": [[0.0, 1.0] for _ in net.sgen.index],
           "storage": [[-1.0, 1.0] for _ in net.storage.index],
           "load_q_bounds": [[float(x), float(y)] for x, y in zip(qlo, qhi)],
           "topologies": [topo0]}
    E._sb_env_path(a.grid).write_text(json.dumps(env, indent=2))
    # coverage on benign test records (monitored loads only)
    p_nom = np.abs(net.load.p_mw.values); q_nom = net.load.q_mvar.values
    ev = S.load_events(root, "test")
    att = [(e["start"] - 60, e.get("recovery", e["end"]) + 60) for e in ev if "benign" not in e["id"]]
    n = nin_p = nin_q = 0
    worst_p = worst_q = 0.0
    for i, rec in enumerate(S.iter_state(root, "test")):
        if i % a.step or any(s0 <= rec["timestamp"] <= e0 for s0, e0 in att):
            continue
        st = rec["state"]
        rp = np.array([st.get(f"load.{k}:active_power", np.nan) for k in net.load.index]) / 1e6 / p_nom
        rq = np.array([st.get(f"load.{k}:reactive_power", np.nan) for k in net.load.index]) / 1e6 / np.where(q_nom == 0, 1, q_nom)
        okp = ~np.isfinite(rp) | ((rp >= lo - a.noise_tol) & (rp <= hi + a.noise_tol))
        okq = ~np.isfinite(rq) | ((rq >= qlo - a.noise_tol) & (rq <= qhi + a.noise_tol))
        n += 1; nin_p += int(okp.all()); nin_q += int(okq.all())
        worst_p = max(worst_p, float(np.nanmax(np.maximum(lo - rp, rp - hi))))
        worst_q = max(worst_q, float(np.nanmax(np.maximum(qlo - rq, rq - qhi))))
    C.GRID = a.grid
    body = f"# Sherlock {a.grid}: a priori envelope from SimBench profiles\n\n"
    body += C.md_table(["quantity", "value"], [
        ["load P bounds", f"SimBench profile min / max per load, widened by {a.margin}"],
        ["load Q bounds", f"transferred from 02-Semiurban train: Q / nominal in [{q_lo_t:.3f}, {q_hi_t:.3f}], widened by {a.margin} (SimBench qload profiles do not describe Sherlock's Q)"],
        ["sgen, storage", "physical ranges [0, 1] of rated, [-1, 1] of nominal"],
        ["initial topology (lines out)", ", ".join(map(str, topo0)) or "none"],
        [f"benign test records sampled (every {a.step}th, more than 60 s from attacks)", n],
        ["records with every monitored load P inside", f"{nin_p} ({nin_p / max(n, 1):.3f}); worst excursion {worst_p:.4f}"],
        ["records with every monitored load Q inside", f"{nin_q} ({nin_q / max(n, 1):.3f}); worst excursion {worst_q:.4f}"],
    ])
    body += "\nNo recorded data was used to build this envelope; the coverage rows only measure it.\n"
    C.write_report(f"{a.grid}_envelope.md", body)
    print(f"topo0 {topo0}; coverage P {nin_p}/{n} worst {worst_p:.4f}; Q {nin_q}/{n} worst {worst_q:.4f}")


if __name__ == "__main__":
    main()
