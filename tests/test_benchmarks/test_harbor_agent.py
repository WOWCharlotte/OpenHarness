"""Tests for benchmarks/harbor_agent.py populate_context_post_run."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock harbor imports before importing harbor_agent
class _MockBaseInstalledAgent:
    pass

class _MockBaseEnvironment:
    pass

class _MockAgentContext:
    def __init__(self):
        self.n_input_tokens = 0
        self.n_output_tokens = 0
        self.n_cache_tokens = 0
        self.cost_usd = None

sys.modules["harbor"] = MagicMock()
sys.modules["harbor.agents"] = MagicMock()
sys.modules["harbor.agents.installed"] = MagicMock()
sys.modules["harbor.agents.installed.base"] = MagicMock()
sys.modules["harbor.agents.installed.base"].BaseInstalledAgent = _MockBaseInstalledAgent
sys.modules["harbor.environments"] = MagicMock()
sys.modules["harbor.environments.base"] = MagicMock()
sys.modules["harbor.environments.base"].BaseEnvironment = _MockBaseEnvironment
sys.modules["harbor.models"] = MagicMock()
sys.modules["harbor.models.agent"] = MagicMock()
sys.modules["harbor.models.agent.context"] = MagicMock()
sys.modules["harbor.models.agent.context"].AgentContext = _MockAgentContext

from benchmarks.harbor_agent import OpenHarnessAgent


class MockAgentContext:
    """Minimal mock for AgentContext."""
    def __init__(self):
        self.n_input_tokens = 0
        self.n_output_tokens = 0
        self.n_cache_tokens = 0
        self.cost_usd = None


# ===== Fixtures =====

@pytest.fixture
def logs_dir(tmp_path: Path) -> Path:
    """Create a temporary logs directory."""
    return tmp_path / "logs"


@pytest.fixture
def run_dir(logs_dir: Path) -> Path:
    """Create run directory under logs."""
    rd = logs_dir / "run"
    rd.mkdir(parents=True, exist_ok=True)
    return rd


@pytest.fixture
def agent(logs_dir: Path) -> OpenHarnessAgent:
    """Create OpenHarnessAgent with mocked dependencies."""
    a = OpenHarnessAgent.__new__(OpenHarnessAgent)
    a.logs_dir = logs_dir
    a.model_name = "minimax-m2.7"
    a.logger = logging.getLogger("test")
    return a


# ===== Tests =====

def test_parse_tool_started_event(run_dir: Path, agent: OpenHarnessAgent):
    """tool_started creates a step with tool_calls."""
    stdout = run_dir / "stdout.txt"
    stdout.write_text(
        '{"type": "tool_started", "tool_name": "bash", "tool_input": {"command": "echo hi"}}\n'
    )

    context = MockAgentContext()
    agent.populate_context_post_run(context)

    trajectory_file = run_dir / "trajectory.json"
    assert trajectory_file.exists()
    data = json.loads(trajectory_file.read_text())
    assert data["schema_version"] == "OH-eval-v1"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["source"] == "agent"
    assert data["steps"][0]["tool_calls"][0]["function_name"] == "bash"
    assert data["steps"][0]["tool_calls"][0]["arguments"] == {"command": "echo hi"}


def test_parse_tool_completed_event(run_dir: Path, agent: OpenHarnessAgent):
    """tool_completed appends observation to matching tool step."""
    stdout = run_dir / "stdout.txt"
    stdout.write_text(
        '{"type": "tool_started", "tool_name": "bash", "tool_input": {"command": "echo hi"}}\n'
        '{"type": "tool_completed", "tool_name": "bash", "output": "hello\\n", "is_error": false}\n'
    )

    context = MockAgentContext()
    agent.populate_context_post_run(context)

    trajectory_file = run_dir / "trajectory.json"
    data = json.loads(trajectory_file.read_text())
    # tool_started creates step 1, tool_completed attaches observation to it
    assert len(data["steps"]) == 1
    assert data["steps"][0]["tool_calls"][0]["function_name"] == "bash"
    assert data["steps"][0]["observation"]["results"][0]["content"] == "hello"
    assert data["steps"][0]["observation"]["results"][0]["is_error"] is False


def test_parse_assistant_message_with_thinking(run_dir: Path, agent: OpenHarnessAgent):
    """assistant_delta accumulates text; thinking block extracted as reasoning_content."""
    stdout = run_dir / "stdout.txt"
    stdout.write_text(
        '{"type": "assistant_delta", "text": "Let me check<thinking>I should look at setup.py first</thinking>the file."}\n'
        '{"type": "assistant_complete", "text": "Let me check<thinking>I should look at setup.py first</thinking>the file."}\n'
    )

    context = MockAgentContext()
    agent.populate_context_post_run(context)

    data = json.loads((run_dir / "trajectory.json").read_text())
    assert data["steps"][0]["message"] == "Let me checkthe file."
    assert "I should look at setup.py first" in data["steps"][0]["reasoning_content"]


def test_parse_mixed_conversation(run_dir: Path, agent: OpenHarnessAgent):
    """Full conversation: assistant msg + tool call + tool result."""
    stdout = run_dir / "stdout.txt"
    stdout.write_text(
        '{"type": "assistant_delta", "text": "Cloning repo."}\n'
        '{"type": "assistant_complete", "text": "Cloning repo."}\n'
        '{"type": "tool_started", "tool_name": "bash", "tool_input": {"command": "git clone https://github.com/foo/bar"}}\n'
        '{"type": "tool_completed", "tool_name": "bash", "output": "done", "is_error": false}\n'
    )

    context = MockAgentContext()
    agent.populate_context_post_run(context)

    data = json.loads((run_dir / "trajectory.json").read_text())
    assert data["final_metrics"]["total_tool_calls"] == 1
    assert data["final_metrics"]["total_errors"] == 0


def test_missing_stdout_graceful(logs_dir: Path, agent: OpenHarnessAgent):
    """Missing stdout.txt does not raise; no trajectory.json written."""
    context = MockAgentContext()
    agent.populate_context_post_run(context)
    assert not (logs_dir / "run" / "trajectory.json").exists()


def test_final_metrics_counts(run_dir: Path, agent: OpenHarnessAgent):
    """final_metrics counts steps, tool_calls, errors correctly."""
    stdout = run_dir / "stdout.txt"
    stdout.write_text(
        '{"type": "tool_started", "tool_name": "bash", "tool_input": {"command": "a"}}\n'
        '{"type": "tool_completed", "tool_name": "bash", "output": "a", "is_error": false}\n'
        '{"type": "tool_started", "tool_name": "bash", "tool_input": {"command": "b"}}\n'
        '{"type": "tool_completed", "tool_name": "bash", "output": "b", "is_error": true}\n'
    )

    context = MockAgentContext()
    agent.populate_context_post_run(context)

    data = json.loads((run_dir / "trajectory.json").read_text())
    # Each tool pair (started+completed) creates 1 step with both tool_calls and observation
    assert data["final_metrics"]["total_steps"] == 2
    assert data["final_metrics"]["total_tool_calls"] == 2
    assert data["final_metrics"]["total_errors"] == 1


def test_unmatched_tool_started_no_completed(run_dir: Path, agent: OpenHarnessAgent):
    """tool_started with no matching tool_completed generates step with null output."""
    stdout = run_dir / "stdout.txt"
    stdout.write_text(
        '{"type": "tool_started", "tool_name": "bash", "tool_input": {"command": "sleep 10"}}\n'
    )

    context = MockAgentContext()
    agent.populate_context_post_run(context)

    data = json.loads((run_dir / "trajectory.json").read_text())
    assert len(data["steps"]) == 1
    assert data["steps"][0]["tool_calls"][0]["function_name"] == "bash"
    # No observation because no tool_completed


def test_agent_context_not_modified_for_tokens(logs_dir: Path, agent: OpenHarnessAgent):
    """AgentContext token fields stay 0; cost stays None."""
    run_dir = logs_dir / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout = run_dir / "stdout.txt"
    stdout.write_text('{"type": "tool_started", "tool_name": "bash", "tool_input": {"command": "x"}}\n')

    context = MockAgentContext()
    agent.populate_context_post_run(context)

    assert context.n_input_tokens == 0
    assert context.n_output_tokens == 0
    assert context.n_cache_tokens == 0
    assert context.cost_usd is None
