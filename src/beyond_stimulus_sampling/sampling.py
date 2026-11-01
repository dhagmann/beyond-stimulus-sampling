"""Reviewed content/style pools and reproducible draws shared within families."""

from __future__ import annotations

import copy
import random
from pathlib import Path

from . import prompts, schemas
from .specification import StudyError, fingerprint, utc_now, validate_study


def sample_family(blueprint: dict, seed: int, replicate: int) -> dict:
    family_id = f"{blueprint['id']}__r{replicate + 1:03d}"
    shared = copy.deepcopy(blueprint)
    pool = shared.pop('sampling', None)
    family = {'id': family_id, 'blueprint': shared}
    if pool is None:
        return family
    content_rng = random.Random(f"{seed}:{family_id}:content")
    style_rng = random.Random(f"{seed}:{family_id}:style")
    indices = content_rng.sample(range(len(pool['content_pool'])), pool['content_per_family'])
    style_index = style_rng.randrange(len(pool['style_pool']))
    shared['required_content'].extend(pool['content_pool'][i] for i in indices)
    shared['argumentation_style'] = pool['style_pool'][style_index]
    family['sampling'] = {'content_indices': indices, 'style_index': style_index,
                          'pool_sha256': fingerprint(pool)}
    return family


def plan(study: dict, provider, cache_dir: Path, *, content_count=15,
         content_per_family=5, style_count=8) -> dict:
    """Propose pools, then require researcher review before any stimulus run."""
    from .workflow import cached_call

    validate_study(study)
    if any(type(x) is not int or x < 1 for x in (content_count, content_per_family, style_count)):
        raise StudyError('Pool sizes and the number of sampled points must be positive integers')
    if content_per_family > content_count:
        raise StudyError('Cannot sample more content points than the pool contains')
    result = copy.deepcopy(study)
    calls = {}

    def check_pool(response):
        for field in ('content_pool', 'style_pool'):
            normalized = [' '.join(text.casefold().split()) for text in response[field]]
            if len(set(normalized)) != len(normalized):
                raise StudyError('Pool suggestions contain duplicate entries; revise the inputs or review a fresh proposal')

    for blueprint in result['blueprints']:
        response, call_id = cached_call(
            cache_dir, provider, prompts.POOL_SYSTEM,
            prompts.pool_prompt(study, blueprint, content_count, style_count),
            schemas.pool_schema(content_count, style_count),
            sample_id=f"pool:{blueprint['id']}", validate_response=check_pool)
        blueprint['sampling'] = {**response, 'content_per_family': content_per_family}
        calls[blueprint['id']] = call_id
    result['pool_provenance'] = {'source_study_sha256': fingerprint(study),
                                 'call_ids': calls, 'created_at': utc_now()}
    result['researcher_review'] = {'completed': False}
    validate_study(result, reviewed=False)
    return result
