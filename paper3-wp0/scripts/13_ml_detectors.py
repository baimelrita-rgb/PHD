"""ML anomaly detectors on Sherlock telemetry (unsupervised: train has no attacks).

Features per 1 Hz IPAL record: bus voltages, line P (from end), transformer P, load / sgen /
storage P divided by nominal, line states, taps, plus first differences of all of them (to
see sudden state changes). Standardised with train statistics.

Models (scikit-learn):
  IF  Isolation Forest, score = -score_samples
  AE  Autoencoder: MLP regressor trained to reproduce its input through a bottleneck,
      score = mean squared reconstruction error
Fit on the first 75 % of train; threshold and persistence calibrated on the last 25 % of
train, which the models never saw: theta = 99.95th percentile of calibration scores,
alarm when the score stays above theta for L records, L = ceil(1.5 x longest calibration
run above theta), at least 3. Evaluated per attack instance and on benign test records.
Alarms are saved for the consolidation loop (WP1-d)."""
import collections
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neural_network import MLPRegressor

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import sherlock_io as S
from p3 import sherlock_model as SM


def physics_features(split):
    """Per-element physics residuals (reported minus recomputed: 15 bus voltages, 15 line P,
    2 transformer P) for every record, from the WP1-a residual model."""
    from p3 import sherlock_residual as SR
    model, out = None, []
    for rec in S.iter_state(S.root(), split):
        if model is None:
            model = SR.ResidualModel(rec["state"]); model.want_vectors = True
        r = model.residual(rec["state"])
        out.append(model.last_vectors if r["conv"] else np.full(32, np.nan))
    return np.nan_to_num(np.array(out))


def features(split, kind="physics"):
    names, net = M.names(), E._base_net()
    idx = M.index()
    semi = E.grid().name == "semiurban"
    keep = [n for n in names if n.split(".")[0] in ("vm_pu", "p_from", "trafo_p_hv", "load_p", "sgen_p", "storage_p", "line_in", "tap", "load_q")]
    scale = np.ones(len(keep))
    for j, n in enumerate(keep):
        k, i = n.split("."); i = int(i)
        if k == "load_p":
            scale[j] = net.load.p_mw.values[i]
        elif k == "sgen_p":
            scale[j] = net.sgen.sn_mva.values[i]
        elif k == "storage_p":
            scale[j] = abs(net.storage.p_mw.values[i]) or 1.0
        elif k == "load_q":
            scale[j] = abs(net.load.q_mvar.values[i]) or 1.0
    cols = [idx[n] for n in keep]
    T, X = [], []
    if semi:   # align with the state-estimation timeline (scripts/17)
        se = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
        want = set(np.round(se[f"{split}_t"], 3))
    for rec in S.iter_state(S.root(), split):
        if semi and round(rec["timestamp"], 3) not in want:
            continue
        T.append(rec["timestamp"])
        X.append(SM.record_measurements(rec["state"], names, net)[cols] / scale)
    X = np.array(X)
    dX = np.vstack([np.zeros((1, X.shape[1])), np.diff(X, axis=0)])
    if kind == "raw":
        return np.array(T), np.hstack([X, dX]), keep
    # physics-informed: residuals plus rates of change, no absolute operating-point values
    if semi:   # partial observability: state-estimation residuals (scripts/17) instead of the D1 power flow
        Rz = np.nan_to_num(np.asarray(se[f"{split}_R"], dtype=float))
        assert len(Rz) == len(X)
    else:
        Rz = physics_features(split)
    return np.array(T), np.hstack([Rz, dX]), [f"res{i}" for i in range(Rz.shape[1])] + keep


def runs(mask):
    out, c = np.zeros(len(mask), int), 0
    for i, x in enumerate(mask):
        c = c + 1 if x else 0
        out[i] = c
    return out


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--pct", type=float, default=99.95)
    ap.add_argument("--run-safety", type=float, default=1.5)
    ap.add_argument("--settle-s", type=float, default=60.0)
    ap.add_argument("--features", default="physics", choices=["physics", "raw"])
    ap.add_argument("--tag", default="", help="suffix for output files (robustness runs)")
    ap.add_argument("--prefix-s", type=float, default=1800.0, help="grids without a train day: train on the first prefix-s seconds of test")
    ap.set_defaults(grid="sherlock")
    a = C.init(ap.parse_args())
    t0 = time.time()
    has_train = any(S.root().glob("train.*.state.gz"))
    if has_train:
        Ttr, Ftr, keep = features("train", a.features)
        Tte, Fte, _ = features("test", a.features)
    else:   # no train day (03-Rural): fit and calibrate on the attack-free prefix of the test day, evaluate after it
        Tte, Fte, keep = features("test", a.features)
        pre = Tte < Tte[0] + a.prefix_s
        Ttr, Ftr = Tte[pre], Fte[pre]
    n_fit = int(0.75 * len(Ftr))
    mu, sd = np.nanmean(Ftr[:n_fit], 0), np.nanstd(Ftr[:n_fit], 0)
    mu = np.nan_to_num(mu)
    sd = np.where(~np.isfinite(sd) | (sd < 1e-6), 1.0, sd)        # constant features (e.g. a line never switched in train) keep scale 1
    Z = lambda F: np.nan_to_num(np.clip((F - mu) / sd, -50, 50))     # unmonitored values (NaN) become 0
    Ztr, Zte = Z(Ftr), Z(Fte)
    fit, cal = Ztr[:n_fit], Ztr[n_fit:]

    models = {}
    iforest = IsolationForest(n_estimators=200, random_state=a.seed, n_jobs=-1).fit(fit[::2])
    models["IF"] = lambda Zx: -iforest.score_samples(Zx)
    ae = MLPRegressor(hidden_layer_sizes=(64, 12, 64), max_iter=60, early_stopping=True, random_state=a.seed)
    ae.fit(fit[::2], fit[::2])
    models["AE"] = lambda Zx: np.mean((ae.predict(Zx) - Zx) ** 2, axis=1)

    ev = S.load_events(S.root(), "test")
    att = [e for e in ev if "benign" not in e["id"]]
    near = np.zeros(len(Tte), bool)
    for e in att:
        near |= (Tte >= e["start"] - a.settle_s) & (Tte <= e.get("recovery", e["end"]) + a.settle_s)
    benign = ~near
    if not has_train:
        benign &= Tte >= Tte[0] + a.prefix_s       # training prefix is not evaluated
    ben_ev = [e for e in ev if "benign" in e["id"]]

    alarms, calib, rows_t = {}, {}, []
    for name, score in models.items():
        s_cal, s_te = score(cal), score(Zte)
        th = float(np.percentile(s_cal, a.pct))
        L = max(3, int(np.ceil(a.run_safety * runs(s_cal > th).max())))
        al = runs(s_te > th) >= L
        alarms[name] = al
        calib[name] = (th, L)
    # D1 physics-residual detector, for comparison and for the ensemble
    if E.grid().name == "semiurban":
        se = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
        assert np.allclose(se["test_t"], Tte)
        phys_name, d1_al = "SE-BDD", se["alarm"].astype(bool)
    else:
        phys_name = "D1"
        d1 = np.load(C.interim("physics_residual_step1.npz"))
        d1_al = np.zeros(len(d1["test_t"]), bool)
        for m_ in ("vm", "p_line", "p_trafo"):
            th = 2.0 * np.nanpercentile(d1[f"train_{m_}"], 99.9)
            L = max(3, int(np.ceil(1.5 * runs(d1[f"train_{m_}"] > th).max())))
            d1_al |= runs(d1[f"test_{m_}"] > th) >= L
        assert np.allclose(d1["test_t"], Tte)
    alarms["D1"] = d1_al
    alarms["D1 or IF or AE"] = alarms["D1"] | alarms["IF"] | alarms["AE"]
    alarms["IF or AE"] = alarms["IF"] | alarms["AE"]
    np.savez_compressed(C.interim(f"detector_alarms_{a.features}{a.tag}.npz"), t=Tte, **{k.replace(" ", "_"): v for k, v in alarms.items()})
    wall = time.time() - t0

    def episodes(mask):
        return int(np.sum(np.diff(np.r_[0, mask.astype(int)]) == 1))

    per_type = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    inst_rows = []
    for e in att:
        sel = (Tte >= e["start"]) & (Tte <= e.get("recovery", e["end"]))
        row = [e["id"], e["description"]]
        for name, al in alarms.items():
            hit = bool(al[sel].any())
            per_type[name][e["description"]][0] += 1
            per_type[name][e["description"]][1] += int(hit)
            row.append(f"{Tte[sel][al[sel]][0] - e['start']:.0f} s" if hit else "no")
        inst_rows.append(row)
    body = f"# ML anomaly detectors on Sherlock telemetry ({a.features} features)\n\n"
    body += ("Unsupervised (train has no attacks). Features: " + (
        "bus voltages, line P, transformer P, load / sgen / storage P over nominal, line states, taps, and their first "
        "differences" if a.features == "raw" else
        "per-element physics residuals (reported minus recomputed bus voltages, line P, transformer P, as in WP1-a) and "
        "first differences of the telemetry (no absolute operating-point values)") + f" ({Ftr.shape[1]} features). Isolation Forest "
             "(200 trees) and an MLP autoencoder (64-12-64), fit on the first 75 % of train. Threshold = "
             f"{a.pct}th percentile of scores on the last 25 % of train (never seen in fitting); alarm when the score stays "
             f"above it for L records, L = ceil({a.run_safety} x longest calibration run), at least 3. D1 is the physics-"
             f"residual detector of WP1-a (on 02-Semiurban the column D1 holds the state-estimation bad-data detector, SE-BDD). Wall time {wall:.0f} s.\n\n")
    body += C.md_table(["detector", "threshold", "L", "false alarm rate, benign test records", "alarm episodes in benign test"],
                       [[n, f"{calib[n][0]:.4g}" if n in calib else "see physics_residual_sherlock.md" if n == "D1" else "OR",
                         calib[n][1] if n in calib else "", f"{alarms[n][benign].mean():.5f}", episodes(alarms[n] & benign)]
                        for n in alarms])
    body += "\n## Detection per attack type (instances detected)\n\n"
    types = sorted({e["description"] for e in att})
    body += C.md_table(["detector"] + types, [[n] + [f"{per_type[n][t][1]}/{per_type[n][t][0]}" for t in types] for n in alarms])
    body += "\n## First alarm after attack start, per instance\n\n"
    body += C.md_table(["id", "type"] + list(alarms), inst_rows)
    # benign false alarm episodes near benign procedures / topologies unseen in train
    fa = alarms["IF or AE"] & benign
    if fa.any():
        near_proc = collections.Counter()
        for t in Tte[fa]:
            lab = "none within 300 s"
            for e in ben_ev:
                if e["start"] - 300 <= t <= e["end"] + 300:
                    lab = e["description"]
            near_proc[lab] += 1
        body += "\nIF or AE false alarm records on benign test, by nearest benign procedure (within 300 s):\n\n"
        body += C.md_table(["benign procedure", "records"], sorted(near_proc.items()))
    C.write_report(f"ml_detectors_{a.features}{a.tag}.md", body)
    for n in alarms:
        print(n, {t: f"{per_type[n][t][1]}/{per_type[n][t][0]}" for t in types}, "FA", f"{alarms[n][benign].mean():.5f}", "episodes", episodes(alarms[n] & benign))
    print(f"{wall:.0f}s")


if __name__ == "__main__":
    main()
