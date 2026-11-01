"""Export only the derived analysis columns needed to compile the manuscript.

Read Qualtrics exports locally. Never copy identifiers, timestamps, demographics,
free-text answers, message texts, IP addresses, or location fields to the output.
"""

from pathlib import Path
import argparse
import csv
import math
import random


LIKERT = {'Not at all': 1, 'Slightly': 2, 'Somewhat': 3, 'Very': 4, 'Extremely': 5}


def qualtrics(path):
    with path.open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.reader(handle)
        header = [name.strip() for name in next(reader)]
        next(reader)  # Question labels.
        next(reader)  # Import IDs.
        for values in reader:
            if len(values) != len(header):
                raise ValueError('Malformed Qualtrics row; no export was written.')
            yield header, values


def field(header, values, name, *, last=False):
    indices = [i for i, text in enumerate(header) if text == name]
    if not indices or (len(indices) > 1 and not last):
        raise ValueError('Missing or ambiguous required analysis column: ' + name)
    return values[indices[-1] if last else indices[0]].strip()


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(columns)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study1', type=Path, required=True)
    parser.add_argument('--study2', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    study1, study2 = [], []
    completed2 = missing2 = 0
    for header, values in qualtrics(args.study1):
        get = lambda name, **kwargs: field(header, values, name, **kwargs)
        if get('Finished') != 'True' or get('Status') != 'IP Address':
            continue
        politics = get('politics', last=True)
        certainty = get('condition').lower()
        assert politics in {'left', 'right'} and certainty in {'low', 'high'}
        persuasion = (-1 if politics == 'left' else 1) * (
            float(get('post_value_1')) - float(get('prior_value_1')))
        study1.append([certainty, persuasion, LIKERT[get('focal_certain')]])
    for header, values in qualtrics(args.study2):
        get = lambda name: field(header, values, name)
        if get('Finished') != 'True' or get('Status') != 'IP Address':
            continue
        completed2 += 1
        if not get('essay'):
            missing2 += 1
            continue
        stance = get('essay_stance')
        assert stance.startswith(('Many', 'Few'))
        certainty, brashness = get('confidence').lower(), get('brashness').lower()
        assert certainty in {'low', 'high'} and brashness in {'low', 'high'}
        persuasion = (1 if stance.startswith('Many') else -1) * (
            float(get('posterior_1')) - float(get('prior_1')))
        study2.append([certainty, brashness, persuasion])
    assert len(study1) == 600 and completed2 == 3200 and missing2 == 15 and len(study2) == 3185
    assert all(math.isfinite(row[1]) and -100 <= row[1] <= 100 for row in study1)
    assert all(math.isfinite(row[2]) and -100 <= row[2] <= 100 for row in study2)
    # Original response order is unnecessary for these analyses.
    random.Random(20261102).shuffle(study1)
    random.Random(20261103).shuffle(study2)
    write_csv(args.output / 'study1_analysis.csv',
              ['certainty', 'persuasion', 'perceived_certainty'], study1)
    write_csv(args.output / 'study2_analysis.csv', ['certainty', 'brashness', 'persuasion'], study2)
    write_csv(args.output / 'sample_flow.csv', ['study', 'completed', 'no_message', 'analyzed'],
              [['study1', 600, 0, 600], ['study2', completed2, missing2, len(study2)]])
    print('Exported analysis-only data: Study 1 n=600; Study 2 n=3185. No raw survey columns were copied.')


if __name__ == '__main__':
    main()
