# Terminal Bench Integration Design

## Overview

Integrate OpenHarness as a `BaseInstalledAgent` in the Harbor framework (v0.3.0) to run Terminal Bench 2.0 evaluations against the `build-cython-ext` feature-building task.

**Goal:** Validate OpenHarness's capability on a real terminal-based coding task.

## Architecture

### Components

| Component | Role |
|-----------|------|
| `benchmarks/harbor_agent.py` | `OpenHarnessAgent` — implements `BaseInstalledAgent` |
| Harbor framework | Downloads tasks, provisions containers, runs agent, verifies results |
| `openharness` package | OpenHarness agent (installed inside container) |
| `oh -p` CLI | Headless single-prompt mode with JSON streaming output |

### Data Flow

```
Harbor runner
  → clones repo, installs OpenHarness in container (install phase)
  → receives task instruction from Harbor
  → runs: oh -p "<instruction>" --output-format stream-json --permission-mode full_auto
  → Harbor verifier checks output
  → reports pass/fail
```

## File to Create

**Path:** `benchmarks/harbor_agent.py`

**Interface:** `BaseInstalledAgent` (from `harbor.agents.installed.base`)

### Class: `OpenHarnessAgent`

```python
from harbor.agents.installed.base import BaseInstalledAgent, ExecInput
from harbor.models.agent.context import AgentContext

class OpenHarnessAgent(BaseInstalledAgent):

    @staticmethod
    def name() -> str:
        return "openharness"   # registered in Harbor's AgentName enum

    @property
    def _install_agent_template_path(self) -> Path:
        # Jinja2 template rendered during install phase
        return Path(__file__).parent / "install_openharness.sh.j2"

    def create_run_agent_commands(self, instruction: str) -> list[ExecInput]:
        # Returns command(s) to run the agent for a given task instruction
        ...

    def populate_context_post_run(self, context: AgentContext) -> None:
        # Optional: parse output files and populate context
        pass
```

### `install()` Phase

Via Jinja2 template (`install_openharness.sh.j2`):

1. Ensure `git` is available (`apt-get install -y git`)
2. Clone from `https://github.com/WOWCharlotte/OpenHarness` into `/home/user/openharness`
3. `pip install -e /home/user/openharness[dev]` (or `uv sync --extra dev` if pip unavailable)

> See [docs/start.md](../../start.md) for full installation reference.

**Provider configuration in container:**
- API keys are passed via `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` env vars (from host through Harbor)
- Model is set via `--model` flag → passed as `OPENHARNESS_MODEL` env var
- If using custom endpoint (e.g. MiniMax), also pass `OPENAI_BASE_URL`
- No `oh provider add` needed — keys passed directly via CLI flags or env vars

### `run()` Phase

```bash
oh -p "<instruction>" \
   --output-format stream-json \
   --permission-mode full_auto \
   --max-turns 50
```

Environment variables passed through `ExecInput.env`:
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (from host)
- `OPENAI_BASE_URL` (if set)
- `OPENHARNESS_MODEL` (Harbor sets model via `--model` flag → maps to `OPENHARNESS_MODEL` env)

## Running the Benchmark

### Test on single task
```bash
harbor run -d "terminal-bench@2.0" \
  --agent-import-path benchmarks.harbor_agent:OpenHarnessAgent \
  --task-names build-cython-ext \
  --model minimax-m2.7 \
  --n-concurrent 1
```

### Feature-building task filter
```bash
harbor run -d "terminal-bench@2.0" \
  --agent-import-path benchmarks.harbor_agent:OpenHarnessAgent \
  --model minimax-m2.7 \
  --n-concurrent 4 \
  --include-task-name "*build*"   # feature building tasks
```

### Local Docker (default)
```bash
export ANTHROPIC_API_KEY=sk-...
harbor run -d "terminal-bench@2.0" \
  --agent-import-path benchmarks.harbor_agent:OpenHarnessAgent \
  --model your-model \
  --n-concurrent 2
```

## File Structure

```
benchmarks/
├── harbor_agent.py           # OpenHarnessAgent (BaseInstalledAgent)
└── install_openharness.sh.j2 # Jinja2 template for container setup
```

## Discovery: Feature-Building Tasks

Identified from `terminal-bench@2.0` task list:

| Task | Category |
|------|----------|
| `build-cython-ext` | Build Cython extension from scratch |
| `build-pov-ray` | Build POV-Ray from source |
| `build-pmars` | Build pmars from source |
| `cobol-modernization` | Modernize COBOL code |
| `code-from-image` | Generate code from image spec |
| `configure-git-webserver` | Configure and build git webserver |
| `financial-document-processor` | Build processor from spec |

## Environment Variables

| Variable | Source | Purpose |
|----------|--------|---------|
| `OPENAI_API_KEY` | Harbor passes from host | API authentication |
| `ANTHROPIC_API_KEY` | Harbor passes from host | API authentication |
| `OPENAI_BASE_URL` | Optional | Custom endpoint |
| `OPENHARNESS_MODEL` | Set from `--model` arg | Model to use |
| `OPENHARNESS_WORKSPACE` | `/app` | Task working directory |

## Error Handling

- **Install failure:** Agent prints error and exits non-zero → Harbor retries
- **Run timeout:** `--max-turns 50` caps execution; Harbor has its own `--agent-timeout-multiplier`
- **Permission denied:** Use `--permission-mode full_auto` to bypass prompts

## Open Questions / Future Improvements

1. **Trajectory logging:** Implement `populate_context_post_run()` to parse `oh` output for token/cost metrics
2. **Pre-built wheels:** Vendor OpenHarness deps for faster container install (Approach B/C)
3. **Custom task filter:** Determine which tasks are truly "feature building" vs. compilation/multi-step
4. **Daytona support:** Add `--env daytona` for cloud scaling
