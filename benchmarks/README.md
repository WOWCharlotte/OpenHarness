# OpenHarness Benchmark Agent for Terminal Bench 2.0

This directory contains the `OpenHarnessAgent` for running OpenHarness benchmarks using [Harbor](https://github.com/HKUDS/Harbor).

## OpenHarnessAgent

`OpenHarnessAgent` is a `BaseInstalledAgent` implementation that runs OpenHarness (`oh` CLI) inside a Harbor container for Terminal Bench 2.0 evaluation.

### Installation Flow (`install()`)

1. **Ensure git is available** — installs git via apt-get if missing
2. **Clone OpenHarness repo** — shallow clone from GitHub
3. **Ensure Python >= 3.10** — installs standalone Python 3.12 if system Python is too old
4. **Install dependencies** — `pip install -e .[dev]`
5. **Configure provider** — sets up `minimax-endpoint` profile
6. **Run debug test** — executes `test_api_resolution_debug.py` to verify settings

### Runtime Flow (`run()`)

Executes the `oh` CLI with the following parameters:

```bash
oh -p "<instruction>" \
  -k <OPENAI_API_KEY> \
  -m <model_name> \
  --base-url <OPENAI_BASE_URL> \
  --api-format openai \
  --permission-mode full_auto \
  --output-format stream-json \
  --max-turns 100
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | MiniMax API key |
| `OPENAI_BASE_URL` | No | Defaults to `https://api.minimaxi.com/v1` |

### Provider Configuration

The agent configures a `minimax-endpoint` profile:

- **Provider**: `anthropic`
- **API Format**: `openai` (OpenAI-compatible)
- **Base URL**: `https://api.minimaxi.com/v1`
- **Auth Source**: `anthropic_api_key`
- **Model**: `minimax-m2.7`

## Usage

### Basic Run Command

```bash
export OPENAI_API_KEY="your-minimax-api-key"
harbor run -d "terminal-bench@2.0" \
  --agent-import-path benchmarks.harbor_agent:OpenHarnessAgent \
  --task-names build-cython-ext \
  --model minimax-m2.7 \
  --n-concurrent 1
```

### Available Task Names

Replace `build-cython-ext` with any Terminal Bench 2.0 task, for example:
- `sed-replace`
- `git-conflict`
- `regex-extract`
- (see Terminal Bench 2.0 task catalog for full list)

### Run Multiple Tasks

```bash
harbor run -d "terminal-bench@2.0" \
  --agent-import-path benchmarks.harbor_agent:OpenHarnessAgent \
  --task-names build-cython-ext sed-replace git-conflict \
  --model minimax-m2.7 \
  --n-concurrent 3
```

### Environment Setup

Ensure `OPENAI_API_KEY` is set in your environment before running:

```bash
export OPENAI_API_KEY="your-minimax-api-key"
```

## Output

After each run, Harbor saves output files:
- `logs/run/return-code.txt` — exit code
- `logs/run/stdout.txt` — stdout (stream-json format)
- `logs/run/stderr.txt` — stderr

## Troubleshooting

### API Resolution Debug Test Fails

If `test_api_resolution_debug.py` fails during install, check:
1. `OPENAI_API_KEY` is correctly set
2. `OPENAI_BASE_URL` is reachable from the container
3. The MiniMax API key has valid permissions

### Provider Add Fails

The `provider add` command may fail if the profile already exists. This is non-fatal and the agent will continue.

### API Key Not Found

The agent passes the API key directly via `-k` to bypass credential storage lookup. If you see auth errors, ensure `OPENAI_API_KEY` is properly exported in the shell running `harbor run`.
