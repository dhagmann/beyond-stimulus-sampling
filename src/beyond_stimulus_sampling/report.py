"""A self-contained, escaped HTML record for researcher inspection."""

from __future__ import annotations

from html import escape
import os
from pathlib import Path
from statistics import mean
from urllib.parse import quote

from .specification import StudyError, dimension_summary, load_json, protect_run_artifact
from .workflow import _attempt_paths, validate_run, family_writer


def _table(headers, rows):
    esc = lambda value: escape(str(value), quote=True)
    return ('<table><thead><tr>' + ''.join('<th>' + esc(h) + '</th>' for h in headers)
            + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + esc(v) + '</td>'
            for v in row) + '</tr>' for row in rows) + '</tbody></table>')


def _relative_link(path, directory):
    return quote(Path(os.path.relpath(path, directory)).as_posix(), safe='/')


def _write_audit(root, manifest, family, record, output, full_report=None):
    protect_run_artifact(root, output)
    study, decision = manifest['study'], record['decision']
    dims, judges = study['dimensions'], study['generation']['judges']
    esc = lambda value: escape(str(value), quote=True)
    writer = family_writer(study, family)
    title = 'Construct and spillover audit'
    status = 'PASS' if decision['accepted'] else 'REVISE'
    blocks = [f'<h1>{title}</h1>', f'<p><strong>{esc(study["title"])}</strong></p>',
              f'<p>{esc(family["id"])}. Attempt {record["attempt"]}. Model screening: <strong>{status}</strong>.</p>',
              f'<p>{esc(family["blueprint"]["context"])}</p>',
              f'<p>Writer: {esc(writer["model"])}. Ratings: ' +
              ', '.join(f'J{i + 1} = {esc(j["name"])} ({esc(j["model"])})' for i, j in enumerate(judges)) + '.</p>']
    if decision['review_flags']:
        blocks.append('<p class="notice"><strong>Researcher review outstanding.</strong> ' +
                      ' '.join(esc(flag.get('explanation', flag.get('comments', flag['kind'])))
                               for flag in decision['review_flags']) + '</p>')
    blocks.append('<h2>Constructs</h2>' + _table(['Construct', 'Treatment or assessment role', 'Included facets'], [
        [d['name'], d['role'] + (' (not gated)' if d['role'] == 'consequence' else ''),
         ', '.join(f['name'] for f in d.get('facets', []))] for d in dims]))
    lookup = {name: {r['id']: r for r in assessment['messages']}
              for name, assessment in record['judges'].items()}
    def scores(cell_id, metric, construct=False):
        return ' / '.join(f"{(lookup[j['name']][cell_id]['ratings'][metric] if construct else lookup[j['name']][cell_id][metric]):g}"
                          for j in judges)
    blocks.append(f"<h2>Judge ratings ({study['assessment']['scale_min']:g}–{study['assessment']['scale_max']:g})</h2>" + _table(
        ['Assigned conditions', *(d['name'] for d in dims), 'Naturalness'],
        [[', '.join(f'{k}={v}' for k, v in c['levels'].items()),
          *(scores(c['id'], d['id'], True) for d in dims), scores(c['id'], 'naturalness')]
         for c in record['cells']]))
    targets = [c for c in decision['contrasts'] if c['role'] == 'target']
    cells = {c['id']: c for c in record['cells']}
    names = {d['id']: d['name'] for d in dims}
    def comparison(contrast):
        low, high = cells[contrast['low_cell']], cells[contrast['high_cell']]
        factor = contrast['manipulated']
        fixed = ', '.join(f'{names[k]}={v}' for k, v in low['levels'].items() if k != factor)
        label = f"{names[factor]}: {low['levels'][factor]} → {high['levels'][factor]}"
        return label + (f' ({fixed})' if fixed else '')
    blocks.append('<h2>Intended contrasts</h2>' + _table(
        ['Comparison', 'Mean signed difference', 'Minimum', 'Result'],
        [[comparison(c), f"{c['mean_signed']:.2f}",
          f"≥ {c['threshold']:.2f}", 'PASS' if c['passed'] else 'FAIL'] for c in targets]))
    spillovers = []
    for d in dims:
        tests = [c for c in decision['contrasts'] if c['role'] == 'spillover' and c['measured'] == d['id']]
        if tests:
            value = max(c['mean_absolute'] for c in tests)
            spillovers.append([d['name'], f'{value:.2f}', f"≤ {study['assessment']['max_spillover']:.2f}",
                               'PASS' if all(c['passed'] for c in tests) else 'FAIL'])
    if spillovers:
        blocks.append('<h2>Spillover</h2>' + _table(
            ['Attribute', 'Largest mean absolute difference', 'Maximum', 'Result'], spillovers))
    criteria, settings = study['assessment'], study['generation']
    quality = []
    for field, key in [('content_fidelity', 'min_content_fidelity'), ('fluency', 'min_fluency')]:
        observed = min(mean(lookup[j['name']][c['id']][field] for j in judges) for c in record['cells'])
        quality.append([field.replace('_', ' ').capitalize(), f'{observed:.2f}', f"≥ {criteria[key]:.2f}"])
    equivalence = mean(j['content_equivalence'] for j in record['judges'].values())
    naturalness = min(mean(lookup[j['name']][c['id']]['naturalness'] for j in judges) for c in record['cells'])
    counts = list(decision['word_counts'].values())
    quality += [['Content equivalence', f'{equivalence:.2f}', f"≥ {criteria['min_content_fidelity']:.2f}"],
                ['Naturalness', f'{naturalness:.2f}', f"Review below {criteria['naturalness_review_below']:.2f}"],
                ['Words per message', f'{min(counts)}–{max(counts)}', f"{settings['min_words']}–{settings['max_words']}"],
                ['Word-count spread', str(max(counts)-min(counts)), f"≤ {settings['max_word_range']}"]]
    blocks.append('<h2>Other checks</h2>' + _table(['Check', 'Observed', 'Rule'], quality))
    for failure in decision['failures']:
        blocks.append('<p class="failure">' + esc(failure['message']) + '</p>')
    blocks.append('<p class="note">Quality values are the lowest message means across judges. '
                  'Spillover is the largest mean absolute judge difference across relevant matched pairs. '
                  'Target checks also require no judge to reverse the ordering. Model screening requires human validation.</p>')
    if full_report:
        blocks.append(f'<p class="links"><a href="{esc(full_report)}#{esc(family["id"])}">Messages and complete revision history</a></p>')
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Construct and spillover audit</title><style>
@page{size:letter;margin:1in}body{font:10pt/1.25 Arial,sans-serif;color:#23313f;max-width:760px;margin:1.5rem auto;padding:0 .5rem}
h1{font-size:18pt;margin:0 0 7px}h2{font-size:11pt;margin:9px 0 4px}p{margin:4px 0}
table{border-collapse:collapse;width:100%;font-size:9pt}th,td{border-bottom:1px solid #ccd5dc;padding:3px 4px;text-align:left;vertical-align:top}
th{background:#f0f4f7}.notice{background:#fff2d6;padding:5px}.failure{color:#a52331}.note{font-size:8pt;margin-top:7px}
tr{break-inside:avoid}td{overflow-wrap:anywhere}@media print{body{max-width:none;margin:0;padding:0}th,td{padding:2px 4px}.links{display:none}}
</style></head><body>''' + '\n'.join(blocks) + '</body></html>\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding='utf-8')
    return output


def audit(root: Path, family_id: str, output: Path | None = None) -> Path:
    root = Path(root)
    validate_run(root)
    manifest = load_json(root / 'manifest.json')
    family = next((f for f in manifest['families'] if f['id'] == family_id), None)
    if family is None:
        raise StudyError('Unknown family ID; inspect the run manifest or full report')
    paths = _attempt_paths(root, family_id)
    if not paths:
        raise StudyError('This family has no completed assessment yet')
    output = Path(output) if output else root / f'audit_{family_id}.html'
    return _write_audit(root, manifest, family, load_json(paths[-1]), output,
                        _relative_link(root / 'report.html', output.parent)
                        if (root / 'report.html').exists() else None)


def render(root: Path, output: Path | None = None) -> Path:
    root = Path(root)
    output = Path(output) if output else root / 'report.html'
    protect_run_artifact(root, output)
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
        blocks.append(f"<h3 id=\"{esc(family['id'])}\">{esc(family['id'])}</h3><p>{esc(family['blueprint']['context'])}</p>")
        blocks.append('<h4>Shared substantive content</h4><ul>' + ''.join(
            f'<li>{esc(point)}</li>' for point in family['blueprint']['required_content']) + '</ul>')
        if family['blueprint'].get('argumentation_style'):
            blocks.append('<p><strong>Shared argumentation style:</strong> ' +
                          esc(family['blueprint']['argumentation_style']) + '</p>')
        paths = _attempt_paths(root, family["id"])
        if not paths:
            blocks.append("<p>Not yet generated.</p>")
            continue
        compact = output.parent / f"audit_{family['id']}.html"
        if compact.resolve() == output.resolve():
            raise StudyError('Choose a full-report filename that differs from its compact family audits')
        _write_audit(root, manifest, family, load_json(paths[-1]), compact,
                     _relative_link(output, compact.parent))
        blocks.append(f'<p><a href="{esc(_relative_link(compact, output.parent))}">Compact family audit</a></p>')
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
