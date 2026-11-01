"""The researcher-facing command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .onboarding import DEFAULT_MODELS, initialize
from .providers import ModelProvider, ProviderError
from .report import render, audit
from .specification import (StudyError, review_details, load_json, utc_now, writer_profiles,
                            validate_study, write_json)
from .workflow import export_messages, propose, run, validate_run
from .sampling import plan


def add_provider(parser):
    parser.add_argument("--provider", choices=["codex", "claude", "command"])
    parser.add_argument("--model", help="model name available to your installed CLI/provider")
    parser.add_argument("--provider-config", type=Path, help="JSON provider configuration (for custom adapters)")


def provider_config(args, *, optional=False):
    if args.provider_config:
        return load_json(args.provider_config)
    if optional and not args.provider and not args.model:
        return None
    kind = args.provider or "codex"
    if kind == "command":
        raise StudyError("Use --provider-config for a command adapter")
    return {"kind": kind, "model": args.model or DEFAULT_MODELS[kind],
            "effort": "low", "timeout_seconds": 300}


def parser():
    p = argparse.ArgumentParser(description="Guided construction and auditing of experimental messages.")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init", help="define constructs and context, then classify model-suggested attributes")
    init.add_argument("--output", type=Path, default=Path("study.json"))
    init.add_argument("--proposal", type=Path, help="use an existing proposal without another model call")
    init.add_argument("--resume", action="store_true")
    add_provider(init)
    prop = commands.add_parser("propose", help="generate candidates for later researcher review")
    prop.add_argument("--construct", required=True)
    prop.add_argument("--context", required=True)
    prop.add_argument("--output", type=Path, required=True)
    add_provider(prop)
    pools = commands.add_parser('plan', help='propose content and organization pools for researcher review')
    pools.add_argument('study', type=Path)
    pools.add_argument('--output', type=Path, required=True)
    pools.add_argument('--content-pool-size', type=int, default=15)
    pools.add_argument('--content-per-family', type=int, default=5)
    pools.add_argument('--style-pool-size', type=int, default=8)
    add_provider(pools)
    review = commands.add_parser("review", help="inspect the study design and construct decisions")
    review.add_argument("study", type=Path)
    review.add_argument("--complete", action="store_true", help="record researcher review after inspecting a draft")
    generate = commands.add_parser("run", help="generate, screen, and selectively revise message families")
    generate.add_argument("study", type=Path)
    generate.add_argument("--output", type=Path, required=True)
    for action, help_text in (("validate", "replay the full audit without model calls"),
                              ("report", "write a standalone HTML report"),
                              ("export", "export screened messages for human validation")):
        command = commands.add_parser(action, help=help_text)
        command.add_argument("run", type=Path)
        if action in {"report", "export"}:
            command.add_argument("--output", type=Path, required=action == "export")
        if action == "export":
            command.add_argument("--allow-partial", action="store_true")
    demo = commands.add_parser("demo", help="run the labelled synthetic example without model access")
    demo.add_argument("--output", type=Path, default=Path("demo-run"))
    compact = commands.add_parser('audit', help='write a compact printable audit for one family')
    compact.add_argument('run', type=Path)
    compact.add_argument('--family', required=True)
    compact.add_argument('--output', type=Path)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.action == "init":
            initialize(args.output, provider_config=provider_config(args, optional=True),
                       proposal_path=args.proposal, resume=args.resume)
        elif args.action == "propose":
            if args.output.exists():
                raise StudyError("The proposal file already exists; choose another output")
            result = propose(args.construct, args.context, ModelProvider(provider_config(args)),
                             args.output.parent / (args.output.stem + ".setup-calls"))
            write_json(args.output, result)
            print(f"Saved candidate proposal: {args.output}. Review it with bss init --proposal {args.output}")
        elif args.action == 'plan':
            if args.output.exists():
                raise StudyError('The planned study file already exists; choose another output')
            source = load_json(args.study)
            validate_study(source)
            config = provider_config(args, optional=True) or source['generation'].get('writer') or writer_profiles(source)[0]
            planned = plan(source, ModelProvider(config),
                           args.output.parent / (args.output.stem + '.pool-calls'),
                           content_count=args.content_pool_size,
                           content_per_family=args.content_per_family,
                           style_count=args.style_pool_size)
            write_json(args.output, planned)
            print(f'Saved pool suggestions: {args.output}. Inspect the content and styles with bss review; '
                  'researcher acceptance is required before generation.')
        elif args.action == "review":
            study = load_json(args.study)
            validate_study(study, reviewed=False)
            print(review_details(study))
            print("\nConstruct decisions:")
            for d in study.get("candidate_review", []):
                print(f"  {d['construct']['name']}: {d['classification']} — {d['rationale']}")
            print("\nAssessment criteria:\n" + json.dumps(study["assessment"], indent=2))
            if args.complete:
                if input("Accept this study specification for generation? (yes/no): ").strip().lower() == "yes":
                    reviewer = input("Researcher/reviewer name: ").strip()
                    if not reviewer:
                        raise StudyError("A reviewer name is required")
                    study["researcher_review"] = {"completed": True, "reviewer": reviewer, "completed_at": utc_now()}
                    validate_study(study)
                    write_json(args.study, study)
            else:
                print(f"\nResearcher review complete: {bool(study.get('researcher_review', {}).get('completed'))}")
        elif args.action == "run":
            print(json.dumps(run(load_json(args.study), args.output), indent=2))
        elif args.action == "validate":
            print(json.dumps(validate_run(args.run), indent=2))
        elif args.action == "report":
            print(render(args.run, args.output))
        elif args.action == 'audit':
            print(audit(args.run, args.family, args.output))
        elif args.action == "export":
            rows = export_messages(args.run, args.output, allow_partial=args.allow_partial)
            print(f"Exported {len(rows)} model-screened messages to {args.output}; human validation remains necessary.")
        elif args.action == "demo":
            from .demo import demonstrate
            demonstrate(args.output)
        return 0
    except (StudyError, ProviderError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\nStopped. Saved run calls can be reused by repeating the command.", file=sys.stderr)
        return 130
