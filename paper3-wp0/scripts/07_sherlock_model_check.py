"""T7: does pandapower's CIGRE MV (with_der="all") reproduce Sherlock's recorded physics?

G1 failed (no grid model in the download), so this checks a CANDIDATE reconstruction.
For each of N benign train snapshots (ground truth, raw/train/physical.zip):
  * external grid voltage magnitude and angle = recorded bus.0 values
  * load, sgen, storage P and Q = recorded MEASUREMENT values (W, var -> MW, Mvar);
    element in service = recorded is_connected
  * storage sign: pandapower convention (positive = charging); assumption
  * topology: Sherlock's 32 switches cannot be mapped to pandapower elements from the
    download, so open line ends are inferred from the recorded line end currents
    (current exactly 0 at an end -> that end open)
  * transformer taps: the pandapower model has no tap changer; snapshots with a nonzero
    recorded tap position are counted and excluded
Then one AC power flow per snapshot; computed bus voltages, line P and line current are
compared with the recorded values."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandapower as pp
import pandapower.networks as pn

from p3 import common as C
from p3 import sherlock_io as S

from p3.sherlock_model import P_DEAD_W, switch_map, fit_trafo, build, noise_floor  # noqa: E402


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--n-fit", type=int, default=300, help="disjoint snapshots for the transformer parameter fit")
    ap.add_argument("--root", default=str(S.ROOT_DEFAULT))
    a = ap.parse_args()
    root = Path(a.root)
    z, idx = S.physical_index(root, "train")
    rng = np.random.default_rng(a.seed)
    order = rng.permutation(len(idx))
    chosen, n_tap = [], 0
    for k in order:
        snap = S.read_snapshot(z, idx[k][1])["values"]
        if snap["trafo.0.MEASUREMENT.tap_position"] != 0 or snap["trafo.1.MEASUREMENT.tap_position"] != 0:
            n_tap += 1
            continue
        chosen.append((idx[k][0], snap))
        if len(chosen) == a.n:
            break
    n_scanned = n_tap + len(chosen)
    def evaluate(trafo_params=None):
        ev, ep, ei, et, topo, nonconv, allchk, nf = [], [], [], [], {}, 0, [], []
        for ts, snap in chosen:
            net, opened, chk = build(snap, trafo_params)
            allchk += chk
            nf.append(noise_floor(snap, net))
            topo[opened] = topo.get(opened, 0) + 1
            try:
                pp.runpp(net)
            except pp.LoadflowNotConverged:
                nonconv += 1
                continue
            ev.append(np.abs(net.res_bus.vm_pu.values - np.array([snap[f"bus.{b}.MEASUREMENT.voltage"] for b in net.bus.index])))
            lin = net.line.in_service.values & np.isfinite(net.res_line.i_from_ka.values)
            ep.append(np.abs(net.res_line.p_from_mw.values[lin] - np.array([snap[f"line.{l}.MEASUREMENT.active_power_from"] / 1e6 for l in net.line.index])[lin]))
            ei.append(np.abs(net.res_line.i_from_ka.values[lin] * 1e3 - np.array([snap[f"line.{l}.MEASUREMENT.current_from"] for l in net.line.index])[lin]))
            et.append(np.abs(net.res_trafo.p_hv_mw.values - np.array([snap[f"trafo.{t}.MEASUREMENT.active_power_hv"] / 1e6 for t in net.trafo.index])))
        ev, ep, ei, et = (np.concatenate(x) for x in (ev, ep, ei, et))
        return ev, ep, ei, et, topo, nonconv, allchk, nf

    def err_table(ev, ep, ei, et):
        return C.md_table(["quantity", "unit", "mean abs", "95th pct", "max abs"], [
            ["bus voltage magnitude (15 buses)", "pu", f"{ev.mean():.2e}", f"{np.percentile(ev, 95):.2e}", f"{ev.max():.2e}"],
            ["line active power, from end", "MW", f"{ep.mean():.2e}", f"{np.percentile(ep, 95):.2e}", f"{ep.max():.2e}"],
            ["line current, from end", "A", f"{ei.mean():.2e}", f"{np.percentile(ei, 95):.2e}", f"{ei.max():.2e}"],
            ["transformer active power, HV side", "MW", f"{et.mean():.2e}", f"{np.percentile(et, 95):.2e}", f"{et.max():.2e}"],
        ])

    ev, ep, ei, et, topo, nonconv, allchk, nf = evaluate()
    used = {idx[k][1] for k in order[:n_scanned]}
    fit_members = [idx[k][1] for k in order[n_scanned:n_scanned + a.n_fit]]
    assert not (used & set(fit_members))
    tp = fit_trafo(z, fit_members)
    ev2, ep2, ei2, et2, _, nonconv2, _, _ = evaluate(tp)
    body = "# T7 Sherlock model check (candidate reconstruction)\n\n"
    body += ("G1 failed: the download has no grid model. This script tests the candidate "
             "`pandapower.networks.create_cigre_network_mv(with_der=\"all\")` against the recorded ground truth "
             "(`raw/train/physical.zip`). Inputs set from each snapshot: external grid voltage and angle, all load, "
             "sgen and storage P and Q, connection states, and all 32 recorded switch states. "
             "Switches 0 to 7 are pandapower's own switches, in the same order. Switches 8 to 31 are mapped as: switch 8+2l is "
             "the from end of line l, 9+2l the to end (lines 0 to 11). This mapping was inferred from the data: switches 18 and 19 "
             "open together when line 5 is out for cable maintenance; switch 25 is the separator moved in the train "
             "playbook; the IPAL state groups switch 8 with line 0 at bus 1 and switch 28 with line 10 at bus 12. "
             "It is checked below on every open switch. "
             "Storage sign follows pandapower (positive = charging); this is an assumption.\n\n")
    body += C.md_table(["quantity", "value"], [
        ["snapshots scanned (seeded random order, train)", n_scanned],
        ["skipped: nonzero recorded tap position", n_tap],
        ["snapshots compared", len(chosen)],
        ["power flow not converged", nonconv],
        ["open mapped switches whose line end carries |P| < 1 W (mapping check)", f"{sum(allchk)}/{len(allchk)}"],
        ["measurement noise floor: max |line voltage_from - bus voltage| (same quantity recorded twice), pu", f"{max(nf):.2e}"],
        ["seed", a.seed],
    ])
    body += "\nRecorded switch configurations (open switches):\n\n"
    body += C.md_table(["open switches", "snapshots"], [[", ".join(k) or "none", v] for k, v in topo.items()])
    body += "\n## Error, computed minus recorded: pandapower CIGRE MV as published\n\n"
    body += err_table(ev, ep, ei, et)
    net0 = pn.create_cigre_network_mv(with_der="all")
    body += ("\n## Transformer parameters implied by the recorded losses\n\n"
             f"Least-squares fit on {a.n_fit} further train snapshots, disjoint from the {len(chosen)} compared above "
             "(tap 0 only): P_loss = pfe + vkr Sn (S/Sn)^2, Q_loss = q0 + vk_x Sn (S/Sn)^2.\n\n")
    body += C.md_table(["transformer", "snapshots", "vkr % (pandapower)", "vkr % (fit)", "vk % (pandapower)", "vk % (fit)",
                        "pfe kW (pandapower)", "pfe kW (fit)", "i0 % (pandapower)", "i0 % (fit)", "max P-loss residual kW"],
                       [[t, p["n"], net0.trafo.vkr_percent.at[t], f"{p['vkr_percent']:.4f}", f"{net0.trafo.vk_percent.at[t]:.4f}",
                         f"{p['vk_percent']:.4f}", net0.trafo.pfe_kw.at[t], f"{p['pfe_kw']:.3f}", net0.trafo.i0_percent.at[t],
                         f"{p['i0_percent']:.4f}", f"{p['resid_kw']:.3f}"] for t, p in tp.items()])
    body += ("\n## Error, computed minus recorded: same model with the fitted transformer parameters\n\n"
             f"Power flow not converged: {nonconv2}.\n\n")
    body += err_table(ev2, ep2, ei2, et2)
    body += ("\nThe voltage error should be read against the noise floor: Sherlock's recorded values carry noise of "
             "the size given above, on inputs as well as outputs. "
             "These numbers say whether the oracle's model matches the dataset's own physics in the tap-0 states. "
             "Tap positions other than 0 need the tap changer parameters (step size, side, range), which are not in the "
             "download.\n")
    C.write_report("sherlock_model_check.md", body)
    print(f"compared {len(chosen)} (skipped tap {n_tap}); base vm max {ev.max():.2e}, trafo P max {et.max():.2e}; "
          f"fitted vm max {ev2.max():.2e}, trafo P max {et2.max():.2e}")


if __name__ == "__main__":
    main()
