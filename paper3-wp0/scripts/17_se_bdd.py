"""WP2-b: state-estimation bad-data detector (SE-BDD) on 02-Semiurban telemetry.

For every 1 Hz IPAL record: topology from the reported switches (unmonitored switches at
their known fixed state), linear WLS state estimation for that topology (built on demand,
also for topologies never seen in train), normalised measurement residuals. Calibration on
train only: each residual is standardised by its train median and MAD; score = max |z|;
alarm when the score stays above theta = k x train 99.9th percentile for L records,
L = ceil(1.5 x longest train run), at least 3 (same scheme as D1).
Also saves the per-record residual vectors for the ML detector and the consolidation loop."""
import collections
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import sherlock_io as S
from p3 import sherlock_model as SM
from p3 import state_est as SE


def runs(mask):
    out, c = np.zeros(len(mask), int), 0
    for i, x in enumerate(mask):
        c = c + 1 if x else 0
        out[i] = c
    return out


def record_cfg(m, idx, n_lines):
    out = tuple(l for l in range(n_lines) if m[idx[f"line_in.{l}"]] < 0.5)
    return E.Config((), None if not out else (out[0] if len(out) == 1 else out), ())


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--k", type=float, default=2.0)
    ap.add_argument("--run-safety", type=float, default=1.5)
    ap.add_argument("--settle-s", type=float, default=60.0)
    ap.add_argument("--step", type=int, default=5, help="use every step-th 1 Hz record")
    ap.add_argument("--iters", type=int, default=1, help="Gauss-Newton corrections against the AC model")
    ap.set_defaults(grid="semiurban")
    a = C.init(ap.parse_args())
    t0 = time.time()
    names, net, idx = M.names(), E._base_net(), M.index()
    obs = SE.observed_names()
    other_sw = [int(s_) for s_ in net.switch.index if net.switch.et.at[s_] != "l"]
    fixed = SM.fixed_switch_states()
    pos = {n: k for k, n in enumerate(obs)}
    data = {}
    n_cfg = collections.Counter()
    for split in ("train", "test"):
        T, Rv, cfgs_seen, skipped = [], [], [], 0
        for i_rec, rec in enumerate(S.iter_state(S.root(), split)):
            if i_rec % a.step:
                continue
            st = rec["state"]
            if any(not st.get(f"switch.{s_}:is_closed", fixed[s_]) for s_ in other_sw):
                skipped += 1
                T.append(rec["timestamp"]); Rv.append(np.full(len(obs), np.nan)); cfgs_seen.append(None)
                continue
            m = SM.record_measurements(st, names, net)
            cfg = record_cfg(m, idx, len(net.line))
            s = SE.se(cfg)
            r = np.full(len(obs), np.nan)
            rr, _ = SE.residual_ac(s, m, iters=a.iters)
            if rr is None:
                T.append(rec["timestamp"]); Rv.append(r); cfgs_seen.append(cfg.label)
                continue
            r[[pos[n] for n in s.names]] = rr
            T.append(rec["timestamp"]); Rv.append(r); cfgs_seen.append(cfg.label)
            n_cfg[(split, cfg.label)] += 1
        data[split] = (np.array(T), np.array(Rv, dtype=np.float32), cfgs_seen, skipped)
    Ttr, Rtr, ctr, sk_tr = data["train"]
    Tte, Rte, cte, sk_te = data["test"]
    # residuals are against the AC model and normalised by the measurement noise sigma: no re-standardisation
    med = np.zeros(Rtr.shape[1]); mad = np.ones(Rtr.shape[1])
    score = lambda Rx: np.nanmax(np.abs(Rx), axis=1) if Rx.size else np.zeros(0)
    s_tr, s_te = score(Rtr), score(Rte)
    s_tr = np.nan_to_num(s_tr); s_te = np.nan_to_num(s_te)
    th = a.k * np.percentile(s_tr, 99.9)
    L = max(3, int(np.ceil(a.run_safety * runs(s_tr > th).max())))
    alarm = runs(s_te > th) >= L
    np.savez_compressed(C.interim("se_residuals.npz"), train_t=Ttr, test_t=Tte, train_R=Rtr, test_R=Rte,
                        med=med, mad=mad, alarm=alarm, th=th, L=L, obs=np.array(obs))
    wall = time.time() - t0

    ev = S.load_events(S.root(), "test")
    att = [e for e in ev if "benign" not in e["id"]]
    near = np.zeros(len(Tte), bool)
    for e in att:
        near |= (Tte >= e["start"] - a.settle_s) & (Tte <= e.get("recovery", e["end"]) + a.settle_s)
    benign = ~near
    per = collections.defaultdict(lambda: [0, 0])
    rows = []
    for e in att:
        sel = (Tte >= e["start"]) & (Tte <= e.get("recovery", e["end"]))
        hit = bool(alarm[sel].any())
        per[e["description"]][0] += 1; per[e["description"]][1] += int(hit)
        rows.append([e["id"], e["description"], ", ".join(e.get("attack_point") or []) or "⟨none⟩",
                     f"{np.nanmax(s_te[sel]) / th:.2f}" if sel.any() else "", f"{Tte[sel][alarm[sel]][0] - e['start']:.0f} s" if hit else "no"])
    unseen = {c for (sp, c) in n_cfg if sp == "test"} - {c for (sp, c) in n_cfg if sp == "train"}
    fa_unseen = np.array([c in unseen for c in cte]) & benign
    body = "# WP2-b: state-estimation bad-data detector on 02-Semiurban\n\n"
    body += (f"Every {a.step}th record of the 1 Hz IPAL state. State estimation per topology: linear WLS (linearised AC at the "
             f"envelope centre) plus {a.iters} Gauss-Newton correction(s) against the full AC model; monitored measurements "
             f"({len(obs)}, load P and Q included), pseudo-measurements for unmonitored load P and Q from monitored loads of the "
             "same profile, weak prior. Residual = measured minus AC model at the estimate, divided by the noise sigma; "
             "score = max |residual|; alarm when above "
             f"theta = {a.k} x train 99.9th percentile for L consecutive records. Wall time {wall:.0f} s.\n\n")
    body += C.md_table(["quantity", "value"], [
        ["records train / test", f"{len(Ttr)} / {len(Tte)}"],
        ["records skipped (a non-line switch open) train / test", f"{sk_tr} / {sk_te}"],
        ["topologies train / test / test topologies unseen in train", f"{len({c for (sp, c) in n_cfg if sp == 'train'})} / {len({c for (sp, c) in n_cfg if sp == 'test'})} / {len(unseen)}"],
        ["theta, L", f"{th:.2f}, {L}"],
        ["false alarm rate, benign test records", f"{alarm[benign].mean():.5f}"],
        ["benign test records in topologies unseen in train / false alarm rate there", f"{int(fa_unseen.sum())} / {alarm[fa_unseen].mean() if fa_unseen.any() else 0:.5f}"],
    ])
    types = sorted(per)
    body += "\nDetection per attack type:\n\n" + C.md_table(["type", "instances", "detected"], [[t, per[t][0], per[t][1]] for t in types])
    body += "\nPer instance (peak score / theta):\n\n" + C.md_table(["id", "type", "targeted assets", "peak / theta", "first alarm"], rows)
    C.write_report("se_bdd.md", body)
    print({t: f"{per[t][1]}/{per[t][0]}" for t in types}, "FA", f"{alarm[benign].mean():.5f}", "unseen-topology FA", f"{alarm[fa_unseen].mean() if fa_unseen.any() else 0:.5f}", f"{wall:.0f}s")


if __name__ == "__main__":
    main()
