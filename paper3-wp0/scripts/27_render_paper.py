"""Render the manuscript. The source (reports/paper_draft.md) keeps internal traceability: a header
note and, after each number, the generated report it comes from in square brackets. The submission
version drops both, writes unreported values as 'n/r', and is rendered to HTML and A4 PDF
(reports/paper_submission.md, reports/paper_draft.pdf). Figures come from reports/figures/."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "reports" / "paper_draft.md"


def clean(md: str) -> str:
    md = re.sub(r"\A(# [^\n]+\n)\n\*Draft for IEEE[^\n]*\*\n", r"\1", md)            # internal header note
    md = re.sub(r"\s*\[(?:[\w.*\-]+\.md(?:, )?)+\]", "", md)                          # [report.md, other.md]
    md = re.sub(r"\s*\[(?:[\w.*\-]+\.(?:json|md)(?:, )?)+\]", "", md)
    md = md.replace("⟨·⟩", "n/r")
    md = re.sub(r"\n## Reproducibility\n.*?(?=\n## References)", "\n## Reproducibility\n\nCode, scripts and every generated report are available from the authors' repository; each reported number is produced by a named script with a fixed seed. Dataset files are not redistributed; download scripts verify checksums.\n", md, flags=re.S)
    return md


def main(out_dir: str):
    out = Path(out_dir); (out / "figures").mkdir(parents=True, exist_ok=True)
    md = clean(SRC.read_text())
    (ROOT / "reports" / "paper_submission.md").write_text(md)
    for f in (ROOT / "reports" / "figures").glob("*.svg"):
        (out / "figures" / f.name).write_text(re.sub(r"<!DOCTYPE[^>]*>\s*", "", f.read_text(), flags=re.S))
    src_md = out / "paper_submission.md"; src_md.write_text(md)
    html = out / "index.html"
    subprocess.run(["pandoc", str(src_md), "-s", "--mathml", "-H", str(out / "head.html"),
                    "--metadata", "title=From Alerts to Certified Rules", "-o", str(html)], check=True)
    h = html.read_text()
    h = re.sub(r"<title>.*?</title>", "<title>Certified Rules Draft</title>", h)
    h = h.replace('<img src="figures/', '<img style="max-width:100%;display:block;margin:12px auto" src="figures/')
    html.write_text(h)
    js = ("const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage();"
          f"await p.goto('file://{html}');await p.waitForTimeout(2500);await p.emulateMedia({{media:'print'}});"
          f"await p.pdf({{path:'{out / 'paper_draft.pdf'}',format:'A4',printBackground:true,margin:{{top:'20mm',bottom:'20mm',left:'18mm',right:'18mm'}}}});await b.close();}})()")
    subprocess.run(["node", "-e", js], check=True)
    shutil.copy(out / "paper_draft.pdf", ROOT / "reports" / "paper_draft.pdf")
    n = subprocess.run(["pdfinfo", str(out / "paper_draft.pdf")], capture_output=True, text=True).stdout
    print([l for l in n.splitlines() if l.startswith("Pages")], "words", len(md.split()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/paper_render")
