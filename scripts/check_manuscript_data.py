"""Check the explicit allowlist for the manuscript's analysis-only data."""

from pathlib import Path
import csv
import math


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'manuscript/data'
SCHEMAS = {'study1_analysis.csv': ['certainty', 'persuasion', 'perceived_certainty'],
           'study2_analysis.csv': ['certainty', 'brashness', 'persuasion'],
           'sample_flow.csv': ['study', 'completed', 'no_message', 'analyzed']}


def main():
    assert {p.name for p in DATA.glob('*.csv')} == set(SCHEMAS), 'Unexpected data file'
    counts = {}
    for filename, expected in SCHEMAS.items():
        with (DATA / filename).open(newline='', encoding='utf-8') as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames == expected, 'Unexpected or identifying field'
            rows = list(reader)
        assert all(set(row) == set(expected) and None not in row.values() for row in rows)
        counts[filename] = len(rows)
        if filename == 'sample_flow.csv':
            assert rows == [{'study': 'study1', 'completed': '600', 'no_message': '0', 'analyzed': '600'},
                            {'study': 'study2', 'completed': '3200', 'no_message': '15', 'analyzed': '3185'}]
            continue
        for row in rows:
            assert row['certainty'] in {'low', 'high'}
            if 'brashness' in row:
                assert row['brashness'] in {'low', 'high'}
            value = float(row['persuasion'])
            assert math.isfinite(value) and -100 <= value <= 100
            if 'perceived_certainty' in row:
                assert row['perceived_certainty'] in {'1', '2', '3', '4', '5'}
    assert counts['study1_analysis.csv'] == 600 and counts['study2_analysis.csv'] == 3185
    print('Data allowlist passed: only treatment labels, derived outcomes, certainty ratings, and sample counts.')


if __name__ == '__main__':
    main()
