"""Descriptive (test-day, not used for selection): detection of B at the smallest k on the grid whose
realised test-day false-alarm load is at most that of C at its frozen k, per day and seed. Same residuals,
topologies, persistence and scoring as scripts/36 (B needs no compute, so it acts at once)."""
import importlib.util, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
from p3 import common as C, envelope as E, sherlock_io as S
sp = importlib.util.spec_from_file_location("a36", Path(__file__).with_name("36_semiurban_abc.py")); a36 = importlib.util.module_from_spec(sp); sp.loader.exec_module(a36)

def main():
    C.parser(__doc__).parse_args()
    rows = []
    for v in ("", "split", "split_s8", "split_s9", "split_s10", "split_s11"):
        a36.setvar(v or None)
        res = json.loads((C.ROOT / "reports" / "abc" / f"abc_{v or 'recorded'}.json").read_text())
        cname = [n for n in res["results"] if n.startswith("C: per-channel + physics check, calibrated")][0]
        rc = res["results"][cname]; target = rc["eps"] / rc["hours"]
        sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
        obs = list(sb["obs"]); kinds = np.array([n.split(".")[0] for n in obs])
        T, R, L = sb["test_t"], np.abs(sb["test_R"]), int(sb["L"])
        noise = a36.noise_from(sb["train_R"], kinds)
        ev = S.load_events(S.root(), "test"); ben = a36.benign_mask(T, ev)
        att = [e for e in ev if e["description"] in a36.PROCESS and "benign" not in e["id"]]
        best = None
        for k in a36.K_GRID:
            f = a36.runs(np.nanmax(R / (k * noise), axis=1) > 1.0, L)
            eps, hrs, _ = a36.eph(f, T, ben)
            det = sum(bool(f[(T >= e["start"]) & (T <= e.get("recovery", e["end"]))].any()) for e in att)
            if eps / hrs <= target + 1e-9:
                best = (k, det, eps, hrs); break
        rows.append([v or "recorded", f"{sum(rc['out'].values())}/{len(rc['out'])}", f"{rc['eps']} in {rc['hours']:.1f} h",
                     "none on the grid" if best is None else f"k = {best[0]:g}: {best[1]}/{len(att)}", "" if best is None else f"{best[2]} in {best[3]:.1f} h"])
        print(rows[-1])
    os.environ.pop("P3_VARIANT", None)
    body = "# Equal realised load (descriptive)\n\n" + __doc__ + "\n\n" + C.md_table(["day", "C at frozen k: detected", "C false-alarm episodes", "B at equal or lower load: detected", "B false-alarm episodes"], rows)
    (C.ROOT / "reports" / "abc" / "equal_load.md").write_text(body)

if __name__ == "__main__":
    main()
