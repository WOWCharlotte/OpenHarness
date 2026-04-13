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

import os
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

        # Step 5: Configure minimax endpoint provider
        # The API key is passed via ANTHROPIC_API_KEY from host environment at runtime.
        # We pre-configure the provider here so 'oh -m minimax-m2.7' works in the run phase.
        await environment.exec(
            command=(
                "cd /home/user/openharness && "
                "PYTHON=$(command -v python3); "
                "$PYTHON -m openharness.cli provider add minimax-endpoint "
                "  --label 'MiniMax' "
                "  --provider anthropic "
                "  --api-format openai "
                "  --auth-source anthropic_api_key "
                "  --model minimax-m2.7 "
                "  --base-url https://api.minimaxi.com/v1 "
                "2>/dev/null || "
                "echo 'provider add failed (may already exist or oh cli issue - continuing)'; "
                "$PYTHON -m openharness.cli provider use minimax-endpoint "
                "2>/dev/null || true"
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
        api_key: str | None = None
        for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            val = os.environ.get(key)
            if val:
                env[key] = val
                if api_key is None:
                    api_key = val

        # Also pass OPENAI_BASE_URL to ensure correct MiniMax Chinese endpoint.
        base_url = os.environ.get("OPENAI_BASE_URL")
        if not base_url:
            base_url = os.environ.get("OPENAI_BASE_URL", "https://api.minimaxi.com/v1")
        env["OPENAI_BASE_URL"] = base_url

        # Build the oh command
        cmd_parts = ["oh", "-p", escaped_instruction]

        # Pass API key directly via --api-key to bypass credential storage lookup.
        # This avoids issues with profile.credential_slot loading stale/missing keys.
        if api_key:
            cmd_parts.extend(["--api-key", api_key])

        if self.model_name:
            cmd_parts.extend(["-m", self.model_name])

        cmd_parts.extend(
            [
                "--permission-mode",
                "full_auto",
                "--output-format",
                "stream-json",
                "--max-turns",
                "50",
            ]
        )

        command = " ".join(cmd_parts)

        # Debug: print config files inside container
        debug_cmd = (
            "python3 << 'PYEOF'\n"
            "import os, pathlib, json\n"
            "home = pathlib.Path(os.environ.get('HOME', '/root'))\n"
            "cred = home / '.openharness' / 'credentials.json'\n"
            "sett = home / '.openharness' / 'settings.json'\n"
            "print('CRED_FILE:', cred, 'exists:', cred.exists())\n"
            "if cred.exists():\n"
            "    print('CRED:', cred.read_text()[:500])\n"
            "print('SETT_FILE:', sett, 'exists:', sett.exists())\n"
            "if sett.exists():\n"
            "    print('SETT:', sett.read_text()[:800])\n"
            "PYEOF\n"
            "echo '---oh output start---'\n"
        )
        full_command = debug_cmd + command

        result = await environment.exec(
            command=full_command,
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
        Populate context after run() completes.

        OpenHarness outputs stream-json to stdout which Harbor already captured.
        No trajectory parsing needed - Harbor verifier handles pass/fail.
        """
        pass
