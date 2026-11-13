"""T2: draw Latin hypercube samples of the full benign envelope, report acceptance,
per-measurement min/max, runtime. Also cross-checks a subset against pandapower runpp."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--n-check", type=int, default=100, help="samples re-solved with pp.runpp")
    a = ap.parse_args()

    t0 = time.time()
    X, ci, cfgs = E.sample_lhs(E.ENVELOPE_FULL, a.n, seed=a.seed)
    res = C.evaluate_batch(X, ci, cfgs)
    t_eval = time.time() - t0

    conv, ben = res["conv"], res["benign"]
    Mx = res["M"]
    names = M.names()
    idx = M.index()
    vm_cols = [idx[k] for k in names if k.startswith("vm_pu.")]
    ld_cols = [idx[k] for k in names if k.startswith("loading.")]
    low_v = conv & (np.nanmin(Mx[:, vm_cols], axis=1) < E.V_MIN)
    high_v = conv & (np.nanmax(Mx[:, vm_cols], axis=1) > E.V_MAX)
    over_l = conv & (np.nanmax(Mx[:, ld_cols], axis=1) > E.LOADING_MAX)

    # reference cross-check with pandapower runpp
    rng = np.random.default_rng(a.seed)
    chk = rng.choice(a.n, size=min(a.n_check, a.n), replace=False)
    max_err, conv_agree = 0.0, 0
    t1 = time.time()
    for i in chk:
        net = E.run_reference_pf(X[i], cfgs[ci[i]])
        conv_agree += int((net is not None) == conv[i])
        if net is not None and conv[i]:
            m_ref = M.vector_from_net(net)
            max_err = max(max_err, float(np.max(np.abs(m_ref - Mx[i]))))
    t_ref = (time.time() - t1) / len(chk)

    # transformer loading (not an envelope limit in the plan, reported as observation)
    net0 = E._base_net()
    tr_sn = net0.trafo.sn_mva.values
    # approximate transformer loading from HV active power only is not exact; recompute exactly on runpp subset
    tr_load_max = 0.0
    for i in chk:
        if ben[i]:
            net = E.run_reference_pf(X[i], cfgs[ci[i]])
            tr_load_max = max(tr_load_max, float(net.res_trafo.loading_percent.max()))

    np.savez_compressed(C.INTERIM / f"envelope_full_smoke_seed{a.seed}.npz", X=X, ci=ci, **res)

    body = "# T2 benign envelope smoke test\n\n"
    body += "Grid: `pandapower.networks.create_cigre_network_mv(with_der=\"pv_wind\")`.\n\n"
    body += "## Envelope parameters (from `src/p3/envelope.py`)\n\n"
    body += C.md_table(["parameter", "value"], [
        ["per-load active power scaling (pf kept)", f"{E.ENVELOPE_FULL.load_scale}, independent per load, {E.dims().n_load} loads"],
        ["per-DER output of rated (q = 0)", f"{E.ENVELOPE_FULL.der_scale}, {E.dims().n_der} DER"],
        ["discrete topologies (connected, radial, tie switches S1 S2 S3, at most one line out)", len(cfgs)],
        ["transformer taps", "fixed: the CIGRE MV model has no tap changer (tap fields NaN)"],
        ["benign limits", f"vm_pu in [{E.V_MIN}, {E.V_MAX}], line loading <= {E.LOADING_MAX} %"],
    ])
    body += "\nTopologies: " + ", ".join(f"`{c.label}`" for c in cfgs) + "\n\n"
    body += "## Acceptance\n\n"
    body += C.md_table(["quantity", "value"], [
        ["samples (Latin hypercube)", a.n],
        ["seed", a.seed],
        ["power flow converged", int(conv.sum())],
        ["rejected: not converged", int((~conv).sum())],
        ["rejected or flagged: some bus below 0.90 pu", int(low_v.sum())],
        ["rejected or flagged: some bus above 1.10 pu", int(high_v.sum())],
        ["rejected or flagged: some line above 100 %", int(over_l.sum())],
        ["accepted (benign)", int(ben.sum())],
        ["acceptance rate", C.fmt(ben.mean())],
        ["runtime, fast AC solver, total s", C.fmt(t_eval, 2)],
        ["runtime per power flow, fast solver, ms", C.fmt(1000 * t_eval / a.n, 3)],
        ["runtime per power flow, pandapower runpp, ms", C.fmt(1000 * t_ref, 2)],
        [f"fast solver vs runpp: max abs diff over all measurements ({len(chk)} samples)", f"{max_err:.2e}"],
        [f"fast solver vs runpp: convergence agreement", f"{conv_agree}/{len(chk)}"],
        [f"max transformer loading %, benign samples in the runpp subset (observation, not a limit)", C.fmt(tr_load_max, 2)],
    ])
    body += "\nA sample can violate more than one limit, so the rejection rows overlap.\n\n"
    body += "Per-topology acceptance:\n\n"
    rows = []
    for k, c in enumerate(cfgs):
        sel = ci == k
        rows.append([f"`{c.label}`", int(sel.sum()), int(ben[sel].sum()), C.fmt(ben[sel].mean() if sel.any() else np.nan, 3)])
    body += C.md_table(["topology", "samples", "benign", "rate"], rows)
    body += "\n## Per-measurement min and max over benign samples\n\n"
    rows = []
    B = Mx[ben]
    for j, n in enumerate(names):
        rows.append([f"`{n}`", C.fmt(B[:, j].min()), C.fmt(B[:, j].max())])
    body += C.md_table(["measurement", "min", "max"], rows)
    C.write_report("envelope_smoke.md", body)
    print(f"benign {ben.sum()}/{a.n}  eval {t_eval:.1f}s  maxdiff vs runpp {max_err:.2e}")


if __name__ == "__main__":
    main()
