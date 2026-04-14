"""
OpenHarnessAgent - BaseInstalledAgent for Terminal Bench 2.0 evaluation.

Usage:
    harbor run -d "terminal-bench@2.0" \
      --agent-import-path benchmarks.harbor_agent:OpenHarnessAgent \
      --task-names build-cython-ext \
      --model minimax-m2.7 \
      --n-concurrent 1
"""

from __future__ import annotations

import json
import os
import re
import shlex

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class OpenHarnessAgent(BaseInstalledAgent):
    """
    Runs OpenHarness (oh CLI) inside a Harbor container for Terminal Bench.

    install():  clones repo + pip install
    run():      oh -p "<instruction>" --model ... --permission-mode full_auto
    """

    @staticmethod
    def name() -> str:
        """Agent name registered in Harbor."""
        return "openharness"

    async def install(self, environment: BaseEnvironment) -> None:
        """
        Install OpenHarness inside the container.

        Strategy:
        1. Ensure git is available (apt-get only for git - tiny and fast)
        2. Clone OpenHarness repo
        3. Ensure python3 >= 3.10 (standalone install from GitHub if too old)
        4. pip install -e .[dev]
        """
        # Step 1: Ensure git is available
        await environment.exec(
            command=(
                "( command -v git >/dev/null 2>&1 || "
                " ( "
                "   for i in $(seq 1 15); do "
                "     fuser /var/lib/dpkg/lock >/dev/null 2>&1 || break; sleep 2; "
                "   done && "
                "   apt-get update -qq 2>/dev/null && "
                "   apt-get install -y -qq git 2>/dev/null ) "
                ") || true"
            ),
        )

        # Step 2: Clone OpenHarness repo
        await environment.exec(
            command=(
                "if [ -d /home/user/openharness ]; then "
                " echo 'openharness already exists'; "
                "elif command -v git >/dev/null 2>&1; then "
                " git clone --depth 1 "
                " https://github.com/WOWCharlotte/OpenHarness.git "
                " /home/user/openharness; "
                "else "
                " echo 'No git, downloading tarball...' && "
                " mkdir -p /home/user/openharness && "
                " URL='https://github.com/WOWCharlotte/OpenHarness/archive/refs/heads/main.tar.gz' && "
                " ( curl -sL \"$URL\" 2>/dev/null || wget -qO- \"$URL\" 2>/dev/null ) "
                " | tar -xz --strip-components=1 -C /home/user/openharness; "
                "fi"
            ),
        )

        # Step 3: Ensure python3 >= 3.10 (standalone install if too old)
        await environment.exec(
            command=(
                "NEED_INSTALL=0; "
                "if command -v python3 >/dev/null 2>&1; then "
                " PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])' 2>/dev/null); "
                " PY_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])' 2>/dev/null); "
                " echo \"python3 found: $(python3 --version) (major=$PY_MAJOR minor=$PY_MINOR)\"; "
                " if [ \"$PY_MAJOR\" -lt 3 ] 2>/dev/null || [ \"$PY_MINOR\" -lt 10 ] 2>/dev/null; then "
                "   echo \"Python $PY_MAJOR.$PY_MINOR is too old (need >= 3.10), upgrading...\"; "
                "   NEED_INSTALL=1; "
                " fi; "
                "else "
                " echo 'No python3 found'; "
                " NEED_INSTALL=1; "
                "fi; "
                "if [ \"$NEED_INSTALL\" = \"1\" ]; then "
                " echo 'Installing standalone Python 3.12 from GitHub...' && "
                " URL='https://github.com/astral-sh/python-build-standalone/releases/"
                "download/20250604/cpython-3.12.11+20250604-x86_64-unknown-linux-gnu-install_only.tar.gz' && "
                " ( curl -sL -o /tmp/python.tar.gz \"$URL\" 2>/dev/null || "
                "   wget -q -O /tmp/python.tar.gz \"$URL\" 2>/dev/null || "
                "   ( apt-get update -qq 2>/dev/null && apt-get install -y -qq curl 2>/dev/null && "
                "     curl -sL -o /tmp/python.tar.gz \"$URL\" ) "
                " ) && "
                " mkdir -p /opt/python && "
                " tar -xzf /tmp/python.tar.gz -C /opt/python --strip-components=1 && "
                " ln -sf /opt/python/bin/python3 /usr/local/bin/python3 && "
                " ln -sf /opt/python/bin/pip3 /usr/local/bin/pip3 && "
                " ln -sf /opt/python/bin/python3 /usr/local/bin/python && "
                " rm -f /tmp/python.tar.gz && "
                " hash -r 2>/dev/null; "
                " echo \"standalone python installed: $(/usr/local/bin/python3 --version)\"; "
                "else "
                " echo 'Python version OK, no upgrade needed'; "
                "fi"
            ),
        )

        # Step 4: pip install -e .[dev]
        await environment.exec(
            command=(
                "PYTHON=$(command -v python3); "
                "cd /home/user/openharness && "
                "if [ -f pyproject.toml ]; then "
                "  $PYTHON -m pip install --break-system-packages -e . 2>/dev/null || "
                "  pip3 install --break-system-packages -e . 2>/dev/null || "
                "  $PYTHON -m pip install --break-system-packages -e .[dev] 2>/dev/null; "
                "fi; "
                "$PYTHON -c 'import openharness; print(\"openharness OK\")' 2>/dev/null || "
                "echo 'openharness installation may have issues but continuing'"
            ),
        )


    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """
        Run OpenHarness for the given task instruction.

        Executes: oh -p "<instruction>" -m <model> --permission-mode full_auto
        """
        escaped_instruction = shlex.quote(instruction)

        # Collect environment variables from host to pass into the container.
        # Harbor does not automatically pass host env vars to the agent process.
        env: dict[str, str] = {}
        openai_api_key: str | None = None
        openai_base_url: str | None = None
        for key in ("OPENAI_API_KEY",):
            val = os.environ.get(key)
            if val:
                env[key] = val
                if openai_api_key is None:
                    openai_api_key = val
        for base_url in ('OPENAI_BASE_URL'):
            val = os.environ.get(base_url,"https://api.minimaxi.com/v1")
            if val:
                env[base_url] = val
                if openai_base_url is None:
                    openai_base_url = val
            

        # Build the oh command with MiniMax OpenAI-compatible endpoint
        cmd_parts = ["oh", "-p", escaped_instruction]

        # Pass API key directly via -k to bypass credential storage lookup.
        if openai_api_key:
            cmd_parts.extend(["-k", openai_api_key])

        if self.model_name:
            cmd_parts.extend(["-m", self.model_name])
        else:
            cmd_parts.extend(["-m", "minimax-m2.7"])  # default to minimax-m2.7 if not specified

        cmd_parts.extend(
            [
                "--base-url",
                openai_base_url,
                "--api-format",
                "openai",
                "--permission-mode",
                "full_auto",
                "--output-format",
                "stream-json",
                "--max-turns",
                "100",
            ]
        )

        command = " ".join(cmd_parts)

        result = await environment.exec(
            command=command,
            timeout_sec=None,  # Harbor manages timeouts
            env=env if env else None,
        )

        # Write output to logs
        logs_dir = self.logs_dir
        run_dir = logs_dir / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "return-code.txt").write_text(str(result.return_code))
        if result.stdout:
            (run_dir / "stdout.txt").write_text(result.stdout)
        if result.stderr:
            (run_dir / "stderr.txt").write_text(result.stderr)

    def populate_context_post_run(self, context: AgentContext) -> None:
        """
        Parse oh -p stream-json output from run/stdout.txt and produce trajectory.json.

        Writes OH-eval-v1 trajectory to {logs_dir}/run/trajectory.json
        and populates AgentContext metrics.
        """
        run_dir = self.logs_dir / "run"
        stdout_path = run_dir / "stdout.txt"

        if not stdout_path.exists():
            self.logger.debug("No stdout.txt found, skipping trajectory generation")
            return

        # --- Two-pass parse ---
        raw_events: list[dict] = []
        with open(stdout_path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw_events.append(json.loads(line))
                except json.JSONDecodeError:
                    self.logger.debug(f"Skipped malformed JSON line {lineno}")
                    continue

        # --- Build pending tool calls (pass 1: pair tool_started with tool_completed) ---
        pending_calls: dict[str, dict] = {}  # tool_name -> event
        tool_pairs: list[tuple[dict, dict | None]] = []  # (started, completed) pairs

        for ev in raw_events:
            ev_type = ev.get("type")
            if ev_type == "tool_started":
                tool_name = str(ev.get("tool_name") or "")
                pending_calls[tool_name] = ev
            elif ev_type == "tool_completed":
                tool_name = str(ev.get("tool_name") or "")
                started = pending_calls.pop(tool_name, None)
                tool_pairs.append((started, ev))

        # Remaining pending = tool_started with no matching tool_completed
        for started in pending_calls.values():
            tool_pairs.append((started, None))

        # --- Build step sequence (pass 2) ---
        from benchmarks.trajectory_schema import (
            Agent,
            FinalMetrics,
            Observation,
            ObservationResult,
            Step,
            ToolCallStep,
            Trajectory,
        )

        steps: list[Step] = []
        current_text_parts: list[str] = []
        current_reasoning_parts: list[str] = []
        step_counter = 0
        pair_index = 0

        for ev in raw_events:
            ev_type = ev.get("type")

            if ev_type == "assistant_delta":
                text = str(ev.get("text") or "")
                current_text_parts.append(text)
                # Extract thinking blocks
                thinking_blocks = re.findall(
                    r"<thinking>(.*?)</thinking>", text, re.DOTALL
                )
                current_reasoning_parts.extend(b.strip() for b in thinking_blocks if b.strip())

            elif ev_type == "assistant_complete":
                # Finalize current assistant message as a step
                full_text = "".join(current_text_parts).strip()
                reasoning = (
                    "\n\n".join(p for p in current_reasoning_parts if p) or None
                )
                # Strip thinking tags from message
                if reasoning:
                    full_text = re.sub(
                        r"<thinking>.*?</thinking>", "", full_text, flags=re.DOTALL
                    ).strip()
                if full_text or reasoning:
                    step_counter += 1
                    steps.append(Step(
                        step_id=step_counter,
                        source="agent",
                        message=full_text or None,
                        reasoning_content=reasoning,
                    ))
                current_text_parts.clear()
                current_reasoning_parts.clear()

            elif ev_type == "tool_started":
                tool_name = str(ev.get("tool_name") or "")
                tool_input = ev.get("tool_input") or {}
                step_counter += 1
                tc_id = f"tool-{pair_index + 1}"
                steps.append(Step(
                    step_id=step_counter,
                    source="agent",
                    tool_calls=[ToolCallStep(
                        tool_call_id=tc_id,
                        function_name=tool_name,
                        arguments=dict(tool_input) if isinstance(tool_input, dict) else {"input": str(tool_input)},
                    )],
                ))
                pair_index += 1

            elif ev_type == "tool_completed":
                # Attach observation to the most recent agent step with matching tool
                tool_name = str(ev.get("tool_name") or "")
                output = ev.get("output")
                is_error = ev.get("is_error")
                if isinstance(output, str):
                    output = output.strip()
                # Backward search for last step with same tool_name
                for step in reversed(steps):
                    if step.tool_calls and step.tool_calls[0].function_name == tool_name:
                        step.observation = Observation(results=[ObservationResult(
                            source_call_id=step.tool_calls[0].tool_call_id,
                            content=output,
                            is_error=bool(is_error) if is_error is not None else None,
                        )])
                        break

        # --- Compute metrics ---
        total_errors = sum(
            1 for s in steps
            if s.observation and s.observation.results
            and s.observation.results[0].is_error
        )
        total_tool_calls = sum(1 for s in steps if s.tool_calls)

        # --- Write trajectory.json ---
        session_id = self.logs_dir.name
        trajectory = Trajectory(
            schema_version="OH-eval-v1",
            session_id=session_id,
            agent=Agent(
                name="openharness",
                version="unknown",
                model_name=self.model_name,
            ),
            steps=steps,
            final_metrics=FinalMetrics(
                total_steps=len(steps),
                total_tool_calls=total_tool_calls,
                total_errors=total_errors,
            ),
        )

        trajectory_path = run_dir / "trajectory.json"
        try:
            with open(trajectory_path, "w", encoding="utf-8") as f:
                json.dump(trajectory.to_dict(), f, indent=2, ensure_ascii=False)
            self.logger.debug(f"Wrote trajectory to {trajectory_path}")
        except OSError as exc:
            self.logger.debug(f"Failed to write trajectory: {exc}")

        # --- Populate AgentContext (token fields stay 0; cost stays None) ---
        context.n_input_tokens = 0
        context.n_output_tokens = 0
        context.n_cache_tokens = 0
        context.cost_usd = None
