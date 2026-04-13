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

import shlex
from pathlib import Path

from harbor.agents.installed.base import BaseInstalledAgent, ExecInput
from harbor.models.agent.context import AgentContext


class OpenHarnessAgent(BaseInstalledAgent):
    """
    Runs OpenHarness (oh CLI) inside a Harbor container for Terminal Bench.

    install() phase:  clones repo + pip install (via install_openharness.sh.j2)
    run() phase:      oh -p "<instruction>" --model ... --permission-mode full_auto
    """

    @staticmethod
    def name() -> str:
        """Agent name registered in Harbor."""
        return "openharness"

    @property
    def _install_agent_template_path(self) -> Path:
        """Path to the Jinja2 shell script template for the install phase."""
        return Path(__file__).parent / "install_openharness.sh.j2"

    def create_run_agent_commands(self, instruction: str) -> list[ExecInput]:
        """
        Build the command to run OpenHarness for a single task instruction.

        Args:
            instruction: The task instruction string from Harbor.

        Returns:
            A single ExecInput with the oh command to execute.
        """
        escaped_instruction = shlex.quote(instruction)

        # Build env dict - Harbor injects API keys via host environment automatically
        env: dict[str, str] = {}

        # Model is passed via --model CLI flag; use it as command-line arg
        model_arg: list[str] = []
        if self.model_name:
            model_arg = ["-m", self.model_name]

        command_parts = [
            "oh",
            "-p",
            escaped_instruction,
            *model_arg,
            "--permission-mode",
            "full_auto",
            "--output-format",
            "stream-json",
            "--max-turns",
            "50",
        ]

        return [
            ExecInput(
                command=" ".join(command_parts),
                cwd=None,  # run in task working directory
                env=env if env else None,
                timeout_sec=None,  # Harbor manages timeouts
            )
        ]

    def populate_context_post_run(self, context: AgentContext) -> None:
        """
        Populate context after run() completes.

        OpenHarness outputs stream-json to stdout which Harbor already captured.
        No trajectory parsing needed - Harbor verifier handles pass/fail.
        """
        pass
