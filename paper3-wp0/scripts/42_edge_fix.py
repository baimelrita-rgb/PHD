"""Edge case of the corner-augmented physics bound (scripts/36): the benign state that still scored 1.02,
and a targeted correction of the remainder estimate.

Phase "reproduce": regenerate the 208 stored-rule corner states of the recorded day exactly as scripts/36
did (affine model of se_proof with the stored margins and seed 7 + 10 x index + 77, the 8 channels with the
largest box maximum relative to the stored margin, both signs, pulled toward the box centre until benign),
score them against the corner-augmented margins (k = 1.5) and report every state above 1: AC convergence,
voltage and loading against the limits, the firing channel, its residual, the affine prediction of the
bound's own affine model, the remainder, box, delta and margin.

Correction (FIXED BEFORE THE REGRESSION AND HOLD-OUT RUN; see git history of this file):
  delta_fix_i = max(delta_aug_i, 1.25 x the largest remainder |r_i - r_aff,i| over the box-corner states of
  the 64 channels with the least slack under the corner-augmented margins at k = 1.5 (slack = margin /
  (box + delta_aug)), both signs, at EVERY benign pull level t in {1, 0.8, 0.6, 0.4, 0.3, 0.2} (scripts/36 kept
  only the first benign level and ranked channels by box / search margin)).
  bound_fix = max(bound, box + delta_fix).
Phase "fix": compute bound_fix for every topology in the caches of scripts/41 and write *_fix caches.
Phase "check": the 208 regression states and a new set never used to choose the correction (64 random box
vertices per topology with new seeds, and the corner states of the channels ranked 65 to 96 by slack), scored
against the fixed margins at k = 1.5; thresholds changed are counted."""
import importlib.util
import json
import pickle
import sys
from multiprocessing import get_context
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import measure as M
from p3 import se_proof as SP
from p3 import state_est as SE

_sp = importlib.util.spec_from_file_location("a36", Path(__file__).with_name("36_semiurban_abc.py"))
a36 = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(a36)
OUT = C.ROOT / "reports" / "topo"
LEVELS = (1.0, 0.8, 0.6, 0.4, 0.3, 0.2)
DAYS = ["recorded", "split", "split_s8", "split_s9", "split_s10", "split_s11"]
G_ = {}


def margin15(b, noise):
    return np.maximum(1.5 * noise[b["opos"]], 1.5 * b["bound"])


def all_levels(cfg, ab, channels):
    out = []
    for i in channels:
        for sgn in (1.0, -1.0):
            xc = np.where(sgn * ab["G"][i] > 0, ab["hi"], ab["lo"])
            for tt in LEVELS:
                x = ab["x0"] + tt * (xc - ab["x0"])
                ok, ben, _, m = M.evaluate(x, cfg)
                if ok and ben:
                    out.append((int(i), sgn, tt, x, m))
    return out


def fix_one(job):
    key, cfg, b = job
    noise = G_["noise"]
    s = SE.se(cfg)
    ab = dict(b["ab"])
    mg = margin15(b, noise)
    slack = mg / (b["box"] + b["delta_aug"])
    ch = np.argsort(slack)[:64]
    rem = np.zeros(len(b["opos"]))
    st = all_levels(cfg, ab, ch)
    for _, _, _, x, m in st:
        r, _ = SE.residual_ac(s, m, iters=a36.ITERS)
        if r is not None:
            rem = np.fmax(rem, np.abs(r - (ab["g"] + ab["G"] @ (x - ab["x0"]))))
    d_fix = np.fmax(b["delta_aug"], 1.25 * rem)
    nb = dict(b); nb["delta_fix"] = d_fix; nb["bound_prefix"] = b["bound"]; nb["bound"] = np.fmax(b["bound"], b["box"] + d_fix)
    nb["slack_rank"] = np.argsort(slack); nb["n_fix_states"] = len(st)
    return key, nb


def score(cfg, s, m, margin):
    r, _ = SE.residual_ac(s, m, iters=a36.ITERS)
    return None if r is None else (np.abs(r) / margin, r)


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--phase", choices=["reproduce", "fix", "check"], required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.set_defaults(grid="semiurban")
    a = C.init(ap.parse_args())
    a36.setvar(None)
    sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    obs = list(sb["obs"]); kinds = np.array([n.split(".")[0] for n in obs]); pos = {n: i for i, n in enumerate(obs)}
    noise = a36.noise_from(sb["train_R"], kinds)
    stored = pickle.loads((C.INTERIM / C.suffixed("semiurban_rules.pkl")).read_bytes())["rules"]
    OUT.mkdir(parents=True, exist_ok=True)
    if a.phase == "reproduce" or a.phase == "check":
        suffix = "" if a.phase == "reproduce" else "_fix"
        cc = pickle.loads((C.INTERIM / f"topo_cache_recorded{suffix}.pkl").read_bytes())
        rows, fails, tot, mx = [], [], 0, 0.0
        for k_, (c, m_st, _) in enumerate(stored):
            b = cc["bounds"][c]; s = SE.se(c); o = np.array([pos[n] for n in s.names])
            assert np.array_equal(o, b["opos"])
            ab0 = SP.affine_bound(c, s, m_st[o], a36.ITERS, 150, 100, 7 + k_ * 10 + 77)
            cs = a36.corner_states(c, ab0, np.argsort(-ab0["box"] / m_st[o])[:8])
            mg = margin15(b, noise)
            for i, sgn, tt, x, m in cs:
                sc = score(c, s, m, mg)
                if sc is None:
                    continue
                tot += 1; mx = max(mx, float(sc[0].max()))
                if sc[0].max() > 1.0:
                    ch = int(np.argmax(sc[0])); r = sc[1]
                    vm_i, ld_i = M._slices()
                    raff = b["ab"]["g"] + b["ab"]["G"] @ (x - b["ab"]["x0"])
                    fails.append({"topology": c.label, "construction": f"corner of channel {s.names[i]} (stored-rule affine), sign {sgn:+.0f}, pulled to {tt}",
                                  "ac": "converged", "voltage_pu": [float(np.nanmin(m[vm_i])), float(np.nanmax(m[vm_i]))], "max_loading_pct": float(np.nanmax(m[ld_i])),
                                  "channel": s.names[ch], "residual": float(r[ch]), "affine_prediction": float(raff[ch]), "remainder": float(r[ch] - raff[ch]),
                                  "box": float(b["box"][ch]), "delta_aug": float(b["delta_aug"][ch]), "delta_fix": float(b.get("delta_fix", b["delta_aug"])[ch]),
                                  "bound": float(b["bound"][ch]), "margin": float(mg[ch]), "score": float(sc[0][ch])})
        res = {"phase": a.phase, "states": tot, "fails": fails, "max_score": mx}
        if a.phase == "check":
            hold, hfails, hmax, changed = 0, 0, 0.0, []
            for j, c in enumerate(cc["order"]):
                b = cc["bounds"][c]; s = SE.se(c); ab = dict(b["ab"]); ab["box"] = b["box"]
                st = a36.vertex_states(c, ab, 64, 424242 + j) + a36.corner_states(c, ab, b["slack_rank"][64:96])
                mg = margin15(b, noise)
                for _, _, _, x, m in st:
                    sc = score(c, s, m, mg)
                    if sc is not None:
                        hold += 1; hmax = max(hmax, float(sc[0].max())); hfails += int(sc[0].max() > 1.0)
                o = b["opos"]
                old = np.maximum(1.5 * noise[o], 1.5 * b["bound_prefix"])
                changed.append([c.label[:60], int(np.sum(mg > old * (1 + 1e-9))), len(o), f"{np.max(mg / old):.2f}"])
            res.update({"holdout_states": hold, "holdout_fails": hfails, "holdout_max": hmax, "thresholds_changed": changed})
        (OUT / f"edge_{a.phase}.json").write_text(json.dumps(res, indent=1))
        print(json.dumps({k: v for k, v in res.items() if k != "thresholds_changed"}, indent=1))
        if a.phase == "check":
            print("\n".join(str(x) for x in res["thresholds_changed"]))
    else:
        for day in DAYS:
            a36.setvar(None if day == "recorded" else day)
            sbd = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
            G_["noise"] = a36.noise_from(sbd["train_R"], kinds)
            cc = pickle.loads((C.INTERIM / f"topo_cache_{day}.pkl").read_bytes())
            items = list(cc["bounds"].items())
            with get_context("fork").Pool(a.workers) as pool:
                res = pool.map(fix_one, [(k, c, b) for k, (c, b) in enumerate(items)])
            nbd = {items[k][0]: nb for k, nb in res}
            cc2 = dict(cc); cc2["bounds"] = nbd
            (C.INTERIM / f"topo_cache_{day}_fix.pkl").write_bytes(pickle.dumps(cc2))
            print(day, "fixed", len(nbd), "topologies", flush=True)
        # train-bound caches used by calibration are the same topologies (contained in the day caches)


if __name__ == "__main__":
    main()
