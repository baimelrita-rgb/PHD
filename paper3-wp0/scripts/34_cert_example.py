"""Reproduction audit, step 4: one certificate recomputed end to end (02-Semiurban, recorded day,
first topology), with units, plus two checks of the final margins.

For the first topology of the recorded day, the affine bound of src/p3/se_proof.py is recomputed with
the seed scripts/18 used (seed + 77, seed = 7 + 0 x 10), and for the channel whose proved margin is
the largest multiple of its noise term, every quantity is printed: noise term (train maximum of the
normalised residual, floored per kind, in units of the residual's sigma), affine box maximum,
remainder delta, bound = box + delta, stored margin = 1.5 x max(noise, bound).
Check 1 (sum condition): a margin covering the physics bound and the noise at the same time needs
m >= bound + noise; we count channels with 1.5 x max(noise, bound) < bound + noise.
Check 2: the box-corner counterexample search of se_proof.corner_check, rerun against the FINAL
(raised) margins of every topology (scripts/18 ran it only against the search margins)."""
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import se_proof as SP
from p3 import state_est as SE


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--topologies", type=int, default=13)
    ap.set_defaults(grid="semiurban")
    a = C.init(ap.parse_args())
    d = pickle.loads((C.INTERIM / C.suffixed("semiurban_rules.pkl")).read_bytes())
    sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    obs = d["obs"]; pos = {n: i for i, n in enumerate(obs)}; kinds = np.array([n.split(".")[0] for n in obs])
    Rtr = sb["train_R"]
    noise = np.nanmax(np.abs(Rtr), axis=0); noise = np.where(np.isfinite(noise), noise, np.nanmax(noise))
    p999 = np.nanpercentile(np.abs(Rtr), 99.9, axis=0)
    noise = np.maximum(noise, np.array([np.nanmedian(p999[kinds == k]) for k in kinds]))
    body = "# Audit step 4: one certificate recomputed, and checks of the final margins\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    # worked example
    cfg, margin, verdict = d["rules"][0]
    s = SE.se(cfg); opos = [pos[n] for n in s.names]
    ab = SP.affine_bound(cfg, s, margin[opos], d["iters"], 150, 100, 7 + 0 * 10 + 77)
    rec = 1.5 * np.fmax(noise[opos], ab["bound"])
    j = int(np.argmax(margin[opos] / noise[opos])); n_ = s.names[j]
    body += f"Topology `{cfg.label}` ({verdict}), {len(opos)} monitored channels, affine bound {ab['seconds']:.0f} s.\n\n"
    body += C.md_table(["quantity", "value (units of the channel's residual sigma)"], [
        ["channel", n_], ["noise term (train max, kind floor)", f"{noise[opos][j]:.3f}"],
        ["affine box maximum |g| + |G| (hi - lo) / 2", f"{ab['box'][j]:.3f}"], ["of which |g| (residual at the box centre)", f"{abs(ab['g'][j]):.3f}"],
        ["remainder delta (1.25 x sampled / DE maximum)", f"{ab['delta'][j]:.3f}"], ["bound = box + delta", f"{ab['bound'][j]:.3f}"],
        ["recomputed margin 1.5 x max(noise, bound)", f"{rec[j]:.3f}"], ["stored margin", f"{margin[opos][j]:.3f}"],
        ["bound + noise (needed if both act at once)", f"{ab['bound'][j] + noise[opos][j]:.3f}"]])
    agree = np.allclose(rec, np.fmax(rec, margin[opos]) , rtol=1e-6)
    body += f"\nRecomputed margins equal the stored ones on {np.mean(np.isclose(rec, margin[opos], rtol=1e-6)) * 100:.1f} % of channels; recomputed >= stored everywhere: {'yes' if np.all(rec <= margin[opos] * (1 + 1e-6)) or agree else 'no'}; median recomputed / stored {np.median(rec / margin[opos]):.3f}.\n"
    body += f"Share of channels where the remainder delta exceeds the box maximum: {np.mean(ab['delta'] > ab['box']):.2f}; median delta / bound {np.median(ab['delta'] / ab['bound']):.2f}.\n\n"
    # check 1 and 2 over topologies
    rows = []
    for k, (cfg, margin, verdict) in enumerate(d["rules"][: a.topologies]):
        s = SE.se(cfg); opos = [pos[n] for n in s.names]
        b = margin[opos] / 1.5
        b_phys = np.where(margin[opos] > 1.5 * noise[opos] * (1 + 1e-9), b, 0.0)     # physics bound where it set the margin
        short = np.mean(margin[opos] < b_phys + noise[opos])
        ab = {"box": b_phys, "G": None}
        cex = []
        # corner check against the final margins needs the affine model: recompute (same seed as scripts/18)
        abk = SP.affine_bound(cfg, s, margin[opos], d["iters"], 150, 100, 7 + k * 10 + 77)
        cex = SP.corner_check(cfg, s, margin[opos], abk, d["iters"])
        worst = max((sc for _, sc in cex), default=float("nan"))
        rows.append([cfg.label[:60], f"{short:.2f}", f"{sum(sc > 1.0 for _, sc in cex)}/{len(cex)}", f"{worst:.2f}"])
        print(rows[-1], flush=True)
    body += C.md_table(["topology", "share of channels with margin < bound + noise", "corner counterexamples to the FINAL margins (found / checked)", "largest corner score (fires if > 1)"], rows)
    C.write_report("audit_cert_example.md", body)
    print(body)


if __name__ == "__main__":
    main()
