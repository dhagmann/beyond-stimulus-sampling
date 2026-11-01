"""Synthetic command-provider fixture. It performs no model or network calls."""

import json
import sys


envelope = json.load(sys.stdin)
assert envelope['allow_tools'] is False
request = json.loads(envelope['prompt'])
if 'focal_construct' in request:
    target = {'name': 'Clarity', 'definition': 'How clear the explanation is.',
              'low_anchor': 'low', 'high_anchor': 'high'}
    response = {'target': target, 'candidates': [
        {**target, 'name': name, 'why_related': 'Synthetic related attribute.',
         'example_change': 'Synthetic illustrative change.'}
        for name in ('Explicitness', 'Warmth', 'Trust')]}
elif 'requested_content_points' in request:
    response = {'content_pool': [f'Synthetic supporting point {i}.' for i in range(request['requested_content_points'])],
                'style_pool': [f'Synthetic organization {i}.' for i in range(request['requested_organizational_styles'])]}
elif 'assigned_perspectives' in request:
    text = {'assignments': {p['construct']: p['perspective'] for p in request['assigned_perspectives']},
            'sample': request['independent_sample_id'], 'revised': 'previous_draft' in request,
            'shared_content': request['required_content'],
            'style': request.get('shared_argumentation_style'),
            'always_fail': envelope['model'] == 'synthetic-always-fail'}
    response = {'text': json.dumps(text)}
else:
    rows = []
    for message in request['messages']:
        data = json.loads(message['text'])
        high = data['assignments']['Clarity'] == 'high'
        bad = high and (not data['revised'] or data['always_fail'])
        scores = {d['id']: (6 if high else 2) if d['name'] == 'Clarity'
                  else (7 if high else 1) if d['name'] == 'Trust' else 4
                  for d in request['dimensions']}
        issues = [{'kind': 'content_changed', 'quote': '"assignments"',
                   'explanation': 'Restore the agreed decision. This is a synthetic test concern.'}] if bad else []
        rows.append({'id': message['id'], 'ratings': scores, 'content_fidelity': 6,
                     'fluency': 6, 'naturalness': 6, 'naturalness_comment': 'Synthetic fixture rating.',
                     'issues': issues})
    response = {'messages': rows, 'content_equivalence': 6,
                'equivalence_explanation': 'Synthetic fixture rating.'}
json.dump(response, sys.stdout)
