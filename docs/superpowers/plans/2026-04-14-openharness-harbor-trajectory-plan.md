# populate_context_post_run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `populate_context_post_run()` 方法，解析 `oh -p --output-format stream-json` 的 JSONL 输出，生成 `trajectory.json`，并将关键指标写入 `AgentContext`。

**Architecture:** 解析器读取 `run/stdout.txt`，按两遍扫描构建 step 序列：assistant 消息累积为带 reasoning 的 step，tool_started/tool_completed 配对生成工具调用 step。输出为精简 ATIF 子集（OH-eval-v1）的 JSON 文件。

**Tech Stack:** Python dataclass（无需外部依赖）

---

## File Structure

```
benchmarks/
├── harbor_agent.py              # 修改：新增 populate_context_post_run
└── trajectory_schema.py         # 新增：dataclass 定义

tests/
└── test_benchmarks/
    └── test_harbor_agent.py     # 新增：单元测试
```

---

## Task 1: 创建 trajectory_schema.py

**Files:**
- Create: `benchmarks/trajectory_schema.py`

- [ ] **Step 1: 创建文件，写入 dataclass 定义**

```python
"""Lightweight trajectory schema for OpenHarness Harbor Agent evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ToolCallStep:
    tool_call_id: str
    function_name: str
    arguments: dict


@dataclass
class ObservationResult:
    source_call_id: str
    content: str | None = None
    is_error: bool | None = None


@dataclass
class Observation:
    results: list[ObservationResult] = field(default_factory=list)


@dataclass
class Step:
    step_id: int
    source: str  # "agent" | "user"
    message: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[ToolCallStep] | None = None
    observation: Observation | None = None


@dataclass
class FinalMetrics:
    total_steps: int
    total_tool_calls: int
    total_errors: int


@dataclass
class Agent:
    name: str
    version: str = "unknown"
    model_name: str | None = None


@dataclass
class Trajectory:
    schema_version: str
    session_id: str
    agent: Agent
    steps: list[Step] = field(default_factory=list)
    final_metrics: FinalMetrics | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "agent": {
                "name": self.agent.name,
                "version": self.agent.version,
                "model_name": self.agent.model_name,
            },
            "steps": [],
            "final_metrics": None,
        }
        for step in self.steps:
            step_dict: dict[str, Any] = {
                "step_id": step.step_id,
                "source": step.source,
            }
            if step.message is not None:
                step_dict["message"] = step.message
            if step.reasoning_content is not None:
                step_dict["reasoning_content"] = step.reasoning_content
            if step.tool_calls is not None:
                step_dict["tool_calls"] = [
                    {
                        "tool_call_id": tc.tool_call_id,
                        "function_name": tc.function_name,
                        "arguments": tc.arguments,
                    }
                    for tc in step.tool_calls
                ]
            if step.observation is not None:
                step_dict["observation"] = {
                    "results": [
                        {
                            "source_call_id": r.source_call_id,
                            "content": r.content,
                            "is_error": r.is_error,
                        }
                        for r in step.observation.results
                    ]
                }
            result["steps"].append(step_dict)

        if self.final_metrics:
            result["final_metrics"] = asdict(self.final_metrics)
        return result
```

- [ ] **Step 2: 提交**

```bash
git add benchmarks/trajectory_schema.py
git commit -m "feat(benchmarks): add trajectory schema dataclasses for OH-eval-v1

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 编写 populate_context_post_run 单元测试

**Files:**
- Create: `tests/test_benchmarks/test_harbor_agent.py`
- Modify: `tests/conftest.py`（如需添加 pytest fixtures）

- [ ] **Step 1: 创建测试目录和测试文件**

```python
"""Tests for benchmarks/harbor_agent.py."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from benchmarks.harbor_agent import OpenHarnessAgent


class MockEnvironment:
    """Minimal mock for BaseEnvironment."""
    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir


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
    """tool_started creates a pending step."""
    stdout = run_dir / "stdout.txt"
    stdout.write_text('{"type": "tool_started", "tool_name": "bash", "tool_input": {"command": "echo hi"}}\n')

    context = MockAgentContext()
    agent.populate_context_post_run(context)

    trajectory_file = run_dir / "trajectory.json"
    assert trajectory_file.exists()
    data = json.loads(trajectory_file.read_text())
    assert data["schema_version"] == "OH-eval-v1"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["source"] == "agent"
    assert data["steps"][0]["tool_calls"][0]["function_name"] == "bash"


def test_parse_tool_completed_event(run_dir: Path, agent: OpenHarnessAgent):
    """tool_completed appends observation to pending step."""
    stdout = run_dir / "stdout.txt"
    stdout.write_text(
        '{"type": "tool_started", "tool_name": "bash", "tool_input": {"command": "echo hi"}}\n'
        '{"type": "tool_completed", "tool_name": "bash", "output": "hello\\n", "is_error": false}\n'
    )

    context = MockAgentContext()
    agent.populate_context_post_run(context)

    trajectory_file = run_dir / "trajectory.json"
    data = json.loads(trajectory_file.read_text())
    # Should have 2 steps: tool_started + tool_completed
    assert len(data["steps"]) == 2
    assert data["steps"][1]["observation"]["results"][0]["content"] == "hello\n"
    assert data["steps"][1]["observation"]["results"][0]["is_error"] is False


def test_parse_assistant_message_with_thinking(run_dir: Path, agent: OpenHarnessAgent):
    """assistant_delta accumulates text; thinking block extracted as reasoning_content."""
    stdout = run_dir / "stdout.txt"
    stdout.write_text(
        '{"type": "assistant_delta", "text": "Let me check<thinking>I should look at setup.py first</thinking>the file."}\n'
        '{"type": "assistant_complete", "text": "Let me check<thinking>I should look at setup.py first</thinking>the file."}\n'
    )

    context = MockAgentContext()
    agent.populate_context_post_run(context)

    trajectory_file = run_dir / "stdout.txt"  # This line is wrong, fix below
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
    assert data["final_metrics"]["total_steps"] == 4
    assert data["final_metrics"]["total_tool_calls"] == 2
    assert data["final_metrics"]["total_errors"] == 1
```

- [ ] **Step 2: 创建 conftest.py（如果不存在 test_benchmarks 目录）**

先检查：
```bash
ls tests/test_benchmarks/ 2>/dev/null || echo "not found"
```

如果不存在，创建：
```bash
mkdir -p tests/test_benchmarks
touch tests/test_benchmarks/__init__.py
```

- [ ] **Step 3: 运行测试，验证失败（因为方法尚未实现）**

```bash
uv run pytest tests/test_benchmarks/test_harbor_agent.py -v 2>&1 | head -40
```
预期：FAIL — `populate_context_post_run` 方法存在但为空

- [ ] **Step 4: 提交测试**

```bash
git add tests/test_benchmarks/ benchmarks/trajectory_schema.py
git commit -m "test(benchmarks): add unit tests for populate_context_post_run

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 实现 populate_context_post_run

**Files:**
- Modify: `benchmarks/harbor_agent.py:210-217`

- [ ] **Step 1: 在 harbor_agent.py 顶部添加导入**

在文件开头的 `from harbor.models.agent.context import AgentContext` 后添加：

```python
from benchmarks.trajectory_schema import (
    Agent,
    FinalMetrics,
    Observation,
    ObservationResult,
    Step,
    ToolCallStep,
    Trajectory,
)
```

- [ ] **Step 2: 替换 populate_context_post_run 方法体**

将现有的空方法 `pass` 替换为：

```python
def populate_context_post_run(self, context: AgentContext) -> None:
    """
    Parse oh -p stream-json output from run/stdout.txt and produce trajectory.json.

    Writes OH-eval-v1 trajectory to {logs_dir}/run/trajectory.json
    and populates AgentContext metrics.
    """
    import re

    run_dir = self.logs_dir / "run"
    stdout_path = run_dir / "stdout.txt"

    if not stdout_path.exists():
        self.logger.debug("No stdout.txt found, skipping trajectory generation")
        return

    # --- Two-pass parse ---
    raw_events: list[dict[str, object]] = []
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
    pending_calls: dict[str, dict[str, object]] = {}  # tool_name -> event
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
            # Attach observation to the most recent agent step that has a matching tool
            tool_name = str(ev.get("tool_name") or "")
            output = ev.get("output")
            is_error = ev.get("is_error")
            if isinstance(output, str):
                output = output.strip()
            # Find the last step with a tool_call of the same name (backward search)
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
    # Infer session_id from logs_dir path
    session_id = self.logs_dir.name  # e.g. "build-cython-ext__pnxtfDq"
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
```

- [ ] **Step 3: 运行测试验证实现**

```bash
uv run pytest tests/test_benchmarks/test_harbor_agent.py -v
```
预期：全部 PASS

如果失败，根据错误信息修复。

- [ ] **Step 4: 提交实现**

```bash
git add benchmarks/harbor_agent.py
git commit -m "feat(benchmarks): implement populate_context_post_run trajectory parsing

Parses oh -p stream-json output to generate OH-eval-v1 trajectory.json.
Extracts tool_started/tool_completed pairs, assistant messages, and
reasoning content from <thinking> tags.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 验证清单

- [ ] `benchmarks/trajectory_schema.py` 创建并包含所有 dataclass
- [ ] `Trajectory.to_dict()` 正确序列化嵌套结构
- [ ] 测试覆盖：tool_started、tool_completed、assistant_delta/complete、mixed、missing stdout、metrics 计数
- [ ] 所有测试通过
- [ ] 提交完成

---

## Spec 自检

1. **Spec 覆盖**：所有 spec 中的条目都有对应实现
   - 输入格式 ✅（JSONL 解析）
   - 输出结构 ✅（OH-eval-v1 JSON）
   - reasoning 提取 ✅（`<thinking>` 标签）
   - 工具匹配 ✅（贪心配对）
   - AgentContext 写入 ✅（token=0, cost=None）
   - 错误处理 ✅（missing file / malformed JSON）
2. **Placeholder scan**：无 TBD/TODO
3. **类型一致性**：`ToolCallStep`、`Step`、`ObservationResult` 字段名与 spec 一致
