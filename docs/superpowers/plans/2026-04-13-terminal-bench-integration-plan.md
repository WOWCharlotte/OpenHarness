# Terminal Bench Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `benchmarks/harbor_agent.py` and `benchmarks/install_openharness.sh.j2` so OpenHarness can run as a BaseInstalledAgent on Terminal Bench 2.0.

**Architecture:** OpenHarnessAgent implements Harbor's `BaseInstalledAgent` interface. The `install()` phase clones the repo and installs the package. The `run()` phase executes `oh -p "<instruction>" --model ...` in headless mode. Harbor's built-in verifier handles pass/fail.

**Tech Stack:** Python 3.10+, Harbor framework (v0.3.0), Jinja2 templates, `openharness-ai` package.

---

## File Structure

```
benchmarks/
├── harbor_agent.py              # OpenHarnessAgent (BaseInstalledAgent implementation)
└── install_openharness.sh.j2   # Jinja2 shell template for container install phase
```

**No existing files are modified.** This is a pure addition — no changes to `src/`, `ohmo/`, or any existing code.

---

## Task 1: Create Jinja2 Install Template

**Files:**
- Create: `benchmarks/install_openharness.sh.j2`

- [ ] **Step 1: Create benchmarks directory**

```bash
mkdir -p benchmarks
```

- [ ] **Step 2: Write install template**

```bash
#!/bin/bash
set -e

# Install system dependencies
apt-get update -qq
apt-get install -y -qq git python3 python3-pip > /dev/null 2>&1

# Clone OpenHarness repo
git clone --depth 1 https://github.com/WOWCharlotte/OpenHarness.git /home/user/openharness

# Install with pip (editable mode with dev extras)
pip install --break-system-packages -e /home/user/openharness[dev]

# Verify installation
python3 -c "import openharness; print('openharness OK')"
```

- [ ] **Step 3: Save file**

Save the template above to `benchmarks/install_openharness.sh.j2`.

- [ ] **Step 4: Commit**

```bash
git add benchmarks/install_openharness.sh.j2
git commit -m "feat(benchmarks): add Jinja2 install template for OpenHarness agent"
```

---

## Task 2: Create OpenHarnessAgent Class

**Files:**
- Create: `benchmarks/harbor_agent.py`
- Reference: `src/openharness/cli.py` (for CLI flag names: `-p`, `--print`, `-m`, `--model`, `--permission-mode`, `--output-format`)

- [ ] **Step 1: Write the harbor_agent.py**

```python
"""
OpenHarnessAgent — BaseInstalledAgent for Terminal Bench 2.0 evaluation.

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
            A single ExecInput with the `oh` command to execute.
        """
        escaped_instruction = shlex.quote(instruction)

        # Build env dict — Harbor injects API keys via host environment automatically
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
                cwd=None,  # run in task's working directory
                env=env if env else None,
                timeout_sec=None,  # Harbor manages timeouts
            )
        ]

    def populate_context_post_run(self, context: AgentContext) -> None:
        """
        Populate context after run() completes.

        OpenHarness outputs stream-json to stdout which Harbor already captured.
        No trajectory parsing needed — Harbor's verifier handles pass/fail.
        """
        pass
```

- [ ] **Step 2: Verify Python syntax**

```bash
python3 -m py_compile benchmarks/harbor_agent.py
```

Expected: no output (success).

- [ ] **Step 3: Commit**

```bash
git add benchmarks/harbor_agent.py benchmarks/install_openharness.sh.j2
git commit -m "feat(benchmarks): add OpenHarnessAgent BaseInstalledAgent for Harbor

- OpenHarnessAgent.run() executes: oh -p '<inst>' -m <model>
  --permission-mode full_auto --output-format stream-json
- install phase uses install_openharness.sh.j2 template"
```

---

## Task 3: Verify Import and Smoke Test

**Files:**
- Modify: none
- Test: `benchmarks/harbor_agent.py`

- [ ] **Step 1: Verify the class can be imported (dry run)**

Since Harbor is not installed locally, do a basic import check:

```bash
python3 -c "
import sys
sys.path.insert(0, 'benchmarks')
# Simulate the import by checking syntax and basic structure
exec(open('benchmarks/harbor_agent.py').read())
print('OpenHarnessAgent defined:', 'OpenHarnessAgent' in dir())
"
```

Expected: `OpenHarnessAgent defined: True`

---

## Verification Command

After all tasks complete, run:

```bash
# Requires Docker daemon running + Harbor installed
harbor run -d "terminal-bench@2.0" \
  --agent-import-path benchmarks.harbor_agent:OpenHarnessAgent \
  --task-names build-cython-ext \
  --model minimax-m2.7 \
  --n-concurrent 1
```

Expected: Harbor downloads task, installs OpenHarness in container, runs `oh -p "<instruction>" ...`, and reports pass/fail via verifier.

---

## Implementation Notes

- **No API key handling needed in code** — Harbor passes `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` from host environment automatically.
- **Model name** comes from `--model` flag → available as `self.model_name` on the agent instance.
- **Trajectory / metrics** — `populate_context_post_run` is a no-op. Future work: parse stream-json output to extract token counts.
- **Timeout** — Harbor manages via `--agent-timeout-multiplier`. OpenHarness caps with `--max-turns 50`.
