"""Structured, stateless model calls with a portable command adapter."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .schemas import validate
from .specification import StudyError, validate_provider


class ProviderError(RuntimeError):
    pass


class ModelProvider:
    """One request per process; responses never inherit another cell's draft."""

    def __init__(self, config: dict[str, Any]):
        validate_provider(config)
        self.config = config
        self._help: str | None = None

    def describe(self) -> dict[str, Any]:
        result = {k: self.config[k] for k in ("kind", "model", "effort", "timeout_seconds")
                  if k in self.config}
        command = self.config.get("command", [self.config["kind"]])
        result["executable"] = Path(command[0]).name
        return result

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.config["kind"] in {"codex", "claude"}:
            # Use the researcher's CLI login, without silently switching to a
            # metered API route because the shell happens to contain an API key.
            for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID",
                        "OPENAI_PROJECT_ID", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
                        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                        "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
                        "AWS_BEARER_TOKEN_BEDROCK", "ANTHROPIC_VERTEX_PROJECT_ID",
                        "ANTHROPIC_FOUNDRY_RESOURCE", "ANTHROPIC_FOUNDRY_API_KEY"):
                env.pop(key, None)
        return env

    def _cli_help(self) -> str:
        if self._help is None:
            argv = ["codex", "exec", "--help"] if self.config["kind"] == "codex" else ["claude", "--help"]
            p = subprocess.run(argv, capture_output=True,
                               text=True, timeout=15, env=self._environment())
            self._help = p.stdout + p.stderr
        return self._help

    def complete(self, system: str, prompt: str, schema: dict) -> tuple[dict, dict]:
        kind, model = self.config["kind"], self.config["model"]
        executable = self.config.get("command", [kind])[0]
        if not shutil.which(executable):
            raise ProviderError(f"{executable} is not installed; choose another provider or use the cached demo")
        with tempfile.TemporaryDirectory(prefix="bss-call-") as temporary:
            temp = Path(temporary)
            schema_path, final_path = temp / "schema.json", temp / "response.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            effort = self.config.get("effort", "low")
            if kind == "codex":
                argv = ["codex", "exec", "--model", model, "--ephemeral"]
                # The server's wrapper supports these flags; ordinary Codex
                # installations can run without the wrapper-specific options.
                help_text = self._cli_help()
                for option in ("--ignore-user-config", "--ignore-rules"):
                    if option in help_text:
                        argv.append(option)
                argv += ["-c", f'model_reasoning_effort="{effort}"',
                         "-c", 'web_search="disabled"', "--sandbox", "read-only",
                         "--color", "never", "--json", "--skip-git-repo-check",
                         "--output-schema", str(schema_path),
                         "--output-last-message", str(final_path), "-"]
                stdin = f"<system_instructions>\n{system}\n</system_instructions>\n\n{prompt}"
            elif kind == "claude":
                argv = ["claude", "-p", "--model", model, "--effort", effort,
                        "--system-prompt", system, "--no-session-persistence",
                        "--tools", "", "--disallowedTools", "mcp__*",
                        "--permission-mode", "dontAsk", "--output-format", "json",
                        "--json-schema", json.dumps(schema, separators=(",", ":"))]
                if "--safe-mode" in self._cli_help():
                    argv.append("--safe-mode")
                else:
                    argv += ["--setting-sources", "", "--strict-mcp-config"]
                stdin = prompt
            else:
                argv = self.config["command"]
                stdin = json.dumps({"system": system, "prompt": prompt, "schema": schema,
                                    "model": model, "effort": effort, "allow_tools": False})
            started = time.monotonic()
            try:
                process = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                                         cwd=temp, env=self._environment(),
                                         timeout=self.config.get("timeout_seconds", 300))
            except subprocess.TimeoutExpired as exc:
                raise ProviderError(f"{kind} exceeded its configured call timeout") from exc
            if process.returncode:
                if kind == "claude":
                    try:
                        error = json.loads(process.stdout)
                    except (json.JSONDecodeError, TypeError):
                        error = {}
                    if isinstance(error, dict) and error.get("api_error") == "usage_limit_reached":
                        raise ProviderError("claude reported a usage limit; resume after it resets, or choose another provider in a new study/run")
                # Neither stderr nor environment variables are copied into
                # research records: provider login errors can contain secrets.
                raise ProviderError(f"{kind} exited with status {process.returncode}; check its login and model name")
            try:
                trace = {}
                if kind == "codex":
                    events = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
                    if not events:
                        raise ProviderError("Codex returned no execution trace")
                    types = [e["item"].get("type") for e in events if isinstance(e.get("item"), dict)]
                    if any(t not in {"agent_message", "reasoning"} for t in types):
                        raise ProviderError("Codex used a tool; supplied-material-only calls cannot be accepted")
                    if not final_path.is_file():
                        raise ProviderError("Codex did not write a structured response")
                    result = json.loads(final_path.read_text())
                    trace = {"item_types": sorted(set(types)), "tools_used": False}
                elif kind == "claude":
                    envelope = json.loads(process.stdout)
                    if envelope.get("is_error"):
                        raise ProviderError("Claude reported an unsuccessful request; check account availability")
                    if envelope.get("permission_denials"):
                        raise ProviderError("Claude attempted a tool call")
                    result = envelope.get("structured_output", envelope.get("result", envelope))
                    if isinstance(result, str):
                        result = json.loads(result)
                    trace = {"turns": envelope.get("num_turns"), "tools_used": False}
                else:
                    result = json.loads(process.stdout)
                    trace = {"tools_used": "adapter responsibility"}
                validate(result, schema)
            except (json.JSONDecodeError, StudyError, TypeError, KeyError) as exc:
                raise ProviderError(f"{kind} returned invalid structured output: {exc}") from exc
            return result, {"provider": self.describe(),
                            "duration_seconds": round(time.monotonic() - started, 3),
                            "execution": trace}
