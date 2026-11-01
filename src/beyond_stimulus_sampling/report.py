"""A self-contained, escaped HTML record for researcher inspection."""

from __future__ import annotations

from html import escape
from pathlib import Path

from .specification import dimension_summary, load_json
from .workflow import _attempt_paths, validate_run


def render(root: Path, output: Path | None = None) -> Path:
    summary = validate_run(root)
    manifest = load_json(root / "manifest.json")
    study = manifest["study"]
    esc = lambda value: escape(str(value), quote=True)
    blocks = [f"<h1>{esc(study['title'])}</h1>",
              "<p class='notice'>Model screening is not human construct validation. Review the messages,"
              " audit unmeasured attributes, and validate the manipulation with the relevant population.</p>",
              f"<p>{summary['screened_families']} / {summary['planned_families']} families screened; "
              f"{summary['screened_messages']} messages; {summary['review_flags']} review flags. "
              f"Corpus {'complete' if summary['complete'] else 'incomplete'}.</p>",
              f"<pre>{esc(dimension_summary(study))}</pre>", "<h2>Construct boundary decisions</h2>"]
    for decision in study.get("candidate_review", []):
        blocks.append(f"<p><strong>{esc(decision['construct']['name'])}</strong>: "
                      f"{esc(decision['classification'])}. {esc(decision['rationale'])}</p>")
    blocks.append("<h2>Message families</h2>")
    for family in manifest["families"]:
        blocks.append(f"<h3>{esc(family['id'])}</h3><p>{esc(family['blueprint']['context'])}</p>")
        paths = _attempt_paths(root, family["id"])
        if not paths:
            blocks.append("<p>Not yet generated.</p>")
            continue
        for path in paths:
            record = load_json(path)
            decision = record["decision"]
            blocks.append(f"<details{' open' if path == paths[-1] else ''}><summary>Attempt "
                          f"{record['attempt']}: {esc(decision['status'])}</summary>")
            for failure in decision["failures"]:
                blocks.append(f"<p class='failure'>{esc(failure['message'])}</p>")
            for flag in decision["review_flags"]:
                blocks.append(f"<p class='notice'>Human review: {esc(flag)}</p>")
            blocks.append("<table><caption>Construct contrasts at fixed levels of other factors</caption>"
                          "<thead><tr><th>Change</th><th>Rated attribute</th><th>Role</th>"
                          "<th>Low → high cells</th><th>Judge differences</th><th>Mean signed</th>"
                          "<th>Mean absolute</th><th>Threshold</th><th>Result</th></tr></thead><tbody>")
            for c in decision["contrasts"]:
                result = "diagnostic" if c["role"] == "consequence" else "pass" if c["passed"] else "fail"
                blocks.append("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in (
                    c["manipulated"], c["measured"], c["role"], f"{c['low_cell']} → {c['high_cell']}",
                    c["by_judge"], f"{c['mean_signed']:.2f}", f"{c['mean_absolute']:.2f}",
                    c["threshold"] if c["threshold"] is not None else "not gated", result)) + "</tr>")
            blocks.append("</tbody></table>")
            for cell in record["cells"]:
                blocks.append(f"<h4>{esc(cell['id'])} · {decision['word_counts'][cell['id']]} words</h4>"
                              f"<div class='message'>{esc(cell['text'])}</div>")
                for name, ratings in record["judges"].items():
                    row = next(r for r in ratings["messages"] if r["id"] == cell["id"])
                    blocks.append(f"<p><strong>{esc(name)}</strong>: {esc(row['ratings'])}; "
                                  f"content {row['content_fidelity']}, fluency {row['fluency']}, "
                                  f"naturalness {row['naturalness']}. {esc(row['naturalness_comment'])}</p>")
                    for issue in row["issues"]:
                        blocks.append(f"<blockquote>{esc(issue['quote'])}</blockquote>"
                                      f"<p>{esc(issue['kind'])}: {esc(issue['explanation'])}</p>")
            blocks.append("</details>")
    blocks.append(f"<h2>Provenance</h2><p>Study SHA-256: <code>{esc(manifest['study_sha256'])}</code>"
                  f"<br>Protocol SHA-256: <code>{esc(manifest['protocol_sha256'])}</code>"
                  f"<br>{summary['checked_attempts']} attempts and {summary['checked_calls']} calls replayed offline.</p>")
    html = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Stimulus audit</title><style>
body{font:17px/1.6 system-ui,sans-serif;color:#222;max-width:1200px;margin:3rem auto;padding:0 1rem}
h1,h2,h3,h4{line-height:1.3}table{border-collapse:collapse;width:100%;font-size:14px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid #ddd;padding:.5rem;text-align:left;vertical-align:top}
.message,pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:1rem}
.notice{background:#fff4d9;padding:.7rem}.failure{color:#9e1c1c}summary{cursor:pointer;font-weight:600}
details{margin:1rem 0}blockquote{border-left:3px solid #aaa;padding-left:1rem}
</style></head><body>""" + "\n".join(blocks) + "</body></html>\n"
    output = output or root / "report.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
