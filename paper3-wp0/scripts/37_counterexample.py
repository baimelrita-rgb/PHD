"""Audit: one benign counterexample to a stored "proved" SE rule, reconstructed to channel level, and the
origin of the stored margin of the worked example (02-Semiurban, recorded day).

Part 1. The stored margin of scripts/18 --prove is m = max(m_search, 1.5 x max(noise, box + delta)),
where m_search = 1.5 x max(noise, largest |r| over the search states) is the margin before the proof step,
and box/delta come from se_proof.affine_bound run with margin_sub = m_search (the DE search for the
remainder is scored relative to m_search). The search step is rerun with the seed scripts/18 used for the
first topology (seed 7) and both components are printed for the worked-example channel.

Part 2. For the topology with the most corner counterexamples (scripts/34), the worst benign corner state is
rebuilt: discrete configuration, envelope parameters (which are at their bounds), AC convergence,
operating-limit check, the channel's residual, its affine prediction, the remainder, the box maximum,
delta, the bound and the stored margin that the state exceeds."""
import importlib.util
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import se_proof as SP
from p3 import state_est as SE

_sp = importlib.util.spec_from_file_location("s18", Path(__file__).with_name("18_semiurban_consolidation.py"))
s18 = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(s18)


def pname(k):
    d = E.dims()
    for lab, n in (("load P scale", d.n_load), ("DER P scale", d.n_der), ("storage P scale", d.n_sto), ("load Q scale", d.n_lq)):
        if k < n:
            return f"{lab} #{k}"
        k -= n
    return f"param {k}"


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--topology", type=int, default=11)
    ap.set_defaults(grid="semiurban")
    a = C.init(ap.parse_args())
    d = pickle.loads((C.INTERIM / C.suffixed("semiurban_rules.pkl")).read_bytes())
    sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    obs = d["obs"]; pos = {n: i for i, n in enumerate(obs)}; kinds = np.array([n.split(".")[0] for n in obs])
    Rtr = sb["train_R"]
    noise = np.nanmax(np.abs(Rtr), axis=0); noise = np.where(np.isfinite(noise), noise, np.nanmax(noise))
    p999 = np.nanpercentile(np.abs(Rtr), 99.9, axis=0)
    noise = np.maximum(noise, np.array([np.nanmedian(p999[kinds == k]) for k in kinds]))
    body = "# Audit: benign counterexample to a stored proved SE rule, and the origin of a stored margin\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    # part 1
    cfg, m_st, _ = d["rules"][0]
    s18.PROVE["on"] = False
    m_search, info = s18.certify_topology(cfg, noise, obs, pos, 40, 150, 7, d["iters"])
    s = SE.se(cfg); o = [pos[n] for n in s.names]
    ab = SP.affine_bound(cfg, s, m_search[o], d["iters"], 150, 100, 7 + 77)
    m_proof = 1.5 * np.fmax(noise[o], ab["bound"])
    m_rec = np.fmax(m_search[o], m_proof)
    j = s.names.index("load_q.6")
    body += "## 1. Worked example, channel load_q.6, first topology\n\n" + C.md_table(["component", "value (sigma units)"], [
        ["noise term", f"{noise[o][j]:.3f}"], ["search margin m_search = 1.5 x max(noise, search maximum)", f"{m_search[o][j]:.3f}"],
        ["affine box + delta (delta scored relative to m_search)", f"{ab['box'][j]:.3f} + {ab['delta'][j]:.3f} = {ab['bound'][j]:.3f}"],
        ["1.5 x max(noise, box + delta)", f"{m_proof[j]:.3f}"], ["max of the two (rule of scripts/18)", f"{m_rec[j]:.3f}"], ["stored margin", f"{m_st[o][j]:.3f}"]])
    body += (f"\nAll channels: stored margin reproduced to 1e-6 relative on {np.mean(np.isclose(m_rec, m_st[o], rtol=1e-6)) * 100:.1f} %; "
             f"search margin larger than the proof margin on {np.mean(m_search[o] > m_proof) * 100:.1f} % of channels "
             f"(a benign search state whose |r| exceeds box + delta, i.e. the affine bound is not an upper bound there).\n\n")
    # part 2
    k = a.topology
    cfg, m_st, _ = d["rules"][k]
    s = SE.se(cfg); o = np.array([pos[n] for n in s.names])
    ab = SP.affine_bound(cfg, s, m_st[o], d["iters"], 150, 100, 7 + k * 10 + 77)
    best = None
    for i in np.argsort(-ab["box"] / m_st[o])[:8]:
        for sgn in (1.0, -1.0):
            xc = np.where(sgn * ab["G"][i] > 0, ab["hi"], ab["lo"])
            for tt in (1.0, 0.8, 0.6, 0.4, 0.3, 0.2):
                x = ab["x0"] + tt * (xc - ab["x0"])
                ok, ben, viol, m = M.evaluate(x, cfg)
                if ok and ben:
                    r, _ = SE.residual_ac(s, m, iters=d["iters"])
                    if r is not None:
                        sc = np.abs(r) / m_st[o]
                        if best is None or sc.max() > best[0]:
                            best = (float(sc.max()), int(np.argmax(sc)), x, m, r, tt, sgn, int(i), viol)
                    break
    sc, ch, x, m, r, tt, sgn, target, viol = best
    vm_i, ld_i = M._slices()
    raff = ab["g"] + ab["G"] @ (x - ab["x0"])
    at_lo = np.isclose(x, ab["lo"]); at_hi = np.isclose(x, ab["hi"])
    contrib = np.abs(ab["G"][ch]) * (ab["hi"] - ab["lo"]) / 2
    top = np.argsort(-contrib)[:6]
    body += f"## 2. Benign corner counterexample, topology {k}: `{cfg.label}`\n\n"
    body += C.md_table(["item", "value"], [
        ["construction", f"box corner maximising the affine residual of channel {s.names[target]} (sign {sgn:+.0f}), pulled to {tt:.1f} of the way from the box centre"],
        ["parameters at lower / upper envelope bound", f"{int(at_lo.sum())} / {int(at_hi.sum())} of {len(x)}"],
        ["AC power flow", "converged"], ["operating limits", f"satisfied (violation {viol:.3g}); bus voltage {np.nanmin(m[vm_i]):.4f} to {np.nanmax(m[vm_i]):.4f} pu (limits {E.V_MIN} to {E.V_MAX}); max loading {np.nanmax(m[ld_i]):.1f} % (limit {E.LOADING_MAX})"],
        ["channel that fires", s.names[ch]], ["state-estimation residual r (sigma units)", f"{r[ch]:+.3f}"],
        ["affine prediction g + G (x - x0)", f"{raff[ch]:+.3f}"], ["remainder r - r_aff", f"{r[ch] - raff[ch]:+.3f}"],
        ["box maximum of |r_aff|", f"{ab['box'][ch]:.3f}"], ["delta (1.25 x sampled / DE remainder)", f"{ab['delta'][ch]:.3f}"],
        ["bound = box + delta", f"{ab['bound'][ch]:.3f}"], ["stored margin", f"{m_st[o][ch]:.3f}"], ["score |r| / margin", f"{sc:.2f} (fires if > 1)"]])
    body += "\nParameters with the largest influence on this channel's affine residual (|G| x half-range):\n\n"
    body += C.md_table(["parameter", "value", "envelope range", "contribution"], [[pname(int(q)), f"{x[q]:.3f}", f"[{ab['lo'][q]:.3f}, {ab['hi'][q]:.3f}]", f"{contrib[q]:.3f}"] for q in top])
    C.write_report("audit_counterexample.md", body)
    print(body)


if __name__ == "__main__":
    main()
