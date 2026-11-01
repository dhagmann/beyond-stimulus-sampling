# Providers and command adapters

The writer, proposer, and each judge use a provider configuration. The wizard asks for an installed CLI and model name. Model names and supported effort levels depend on the provider installation and account; change the study settings to match the models you can access.

```json
{"kind": "codex", "model": "YOUR_MODEL", "effort": "low", "timeout_seconds": 300}
```

`kind` may be `codex`, `claude`, or `command`. Judge entries additionally have a unique `name`. For the two CLI providers, authenticate using that provider's ordinary login. Each call runs in a fresh temporary working directory, without conversation persistence, with instructions to use only the supplied material. The Codex adapter requests structured output, disables web search, uses a read-only sandbox, and rejects traces containing tool items. The Claude adapter disables tools and rejects reported permission denials. Provider-specific user configuration and execution environments can affect behavior; check your installation when reproducing a run.

For CLI providers, the adapter removes API-key and API-base variables from the child environment to use the configured CLI login. It does not rewrite credentials. Command adapters inherit the environment so they can use their own authentication. No provider environment or raw authentication stderr is copied into run records. Complete request payloads **are** archived, including command arguments: credentials belong in environment variables or a login store, never in those arguments or the study file.

## An external model service

To use another service, implement a program that reads one JSON request from standard input and writes one JSON response to standard output. A minimal configuration is:

```json
{
  "kind": "command",
  "model": "your-model-identifier",
  "effort": "low",
  "timeout_seconds": 300,
  "command": ["/absolute/path/to/python", "/absolute/path/to/adapter.py"]
}
```

The request contains `system`, `prompt`, `schema`, `model`, `effort`, and `allow_tools: false`. Parse `prompt` as JSON if you need its structured content. Return the object matching `schema` directly, without a Markdown fence or an API response envelope. The harness checks types, required fields, permitted extra fields, rating ranges, message IDs, and quote evidence. The adapter must implement a stateless call and enforce its own no-tool policy. The harness cannot audit an external service's hidden tool use.

The process is invoked as an argument vector with `shell=False`; no shell command string is evaluated. Use absolute script paths because the working directory is temporary. Keep logs out of standard output. A nonzero exit, timeout, or invalid response stops the run; completed successful calls remain cached for resume. Authentication errors are deliberately summarized without copying raw stderr into the research record.

Save this configuration as `provider.json` and pass it to `bss init --provider-config provider.json` or `bss propose --provider-config provider.json`. A single configuration can be used for all roles, or each role can use a different model. Separate calls to one model do not establish independent validation. Each role/family/attempt has a separate cache identity even if its rendered prompt matches another call.

The setup wizard offers additional writer models and custom judge models. In a study file, `generation.writers` is an optional list of named provider configurations. When present, it controls writing instead of the single `generation.writer` entry. The engine balances profiles across families within each context and fixes a family's assigned writer across its conditions and revisions. See the [study specification](study-specification.md) for an example.
