# OpenHarness Harbor Agent — populate_context_post_run 实现设计

## Overview

为 `OpenHarnessAgent` 实现 `populate_context_post_run()` 方法，解析 `oh -p --output-format stream-json` 的 JSONL 输出，生成结构化轨迹文件 `trajectory.json`，并将关键指标写入 `AgentContext`。

**目标**：在不追求完整 ATIF 兼容的前提下，提供可机器解析、可人工复盘的评测轨迹。

## 输入格式

`oh -p` 在 `--output-format stream-json` 模式下输出的 JSONL 事件类型：

| type | 字段 | 说明 |
|------|------|------|
| `assistant_delta` | `text` | 增量文本流（可含 `<thinking>` 标签） |
| `assistant_complete` | `text` | assistant 消息完成 |
| `tool_started` | `tool_name`, `tool_input` | 工具调用开始 |
| `tool_completed` | `tool_name`, `output`, `is_error` | 工具调用完成 |

**关键约束**：
- 无 timestamp
- 无 session_id
- 无 token 计量
- 工具 ID 通过 `tool_name` 贪心配对

## 输出结构

### 文件：`{logs_dir}/run/trajectory.json`

```json
{
  "schema_version": "OH-eval-v1",
  "session_id": "build-cython-ext__pnxtfDq",
  "agent": {
    "name": "openharness",
    "version": "unknown",
    "model_name": "minimax-m2.7"
  },
  "steps": [
    {
      "step_id": 1,
      "source": "agent",
      "message": "Let me start by cloning the repository...",
      "reasoning_content": "...",
      "tool_calls": [
        {
          "tool_call_id": "tool-1",
          "function_name": "bash",
          "arguments": {"command": "cd /app && git clone ..."}
        }
      ]
    },
    {
      "step_id": 2,
      "source": "agent",
      "observation": {
        "results": [{"source_call_id": "tool-1", "content": "git switch...\n", "is_error": false}]
      }
    }
  ],
  "final_metrics": {
    "total_steps": 42,
    "total_tool_calls": 18,
    "total_errors": 2
  }
}
```

### AgentContext 写入

| 字段 | 值 | 原因 |
|------|-----|------|
| `n_input_tokens` | 0 | 不可用 |
| `n_output_tokens` | 0 | 不可用 |
| `n_cache_tokens` | 0 | 不可用 |
| `cost_usd` | None | 不可用 |

## 解析算法

### 两遍扫描

**第一遍**：收集所有 tool_started / tool_completed 事件，按出现顺序配对

```
tool_started{bash} → tool_completed{bash}  → pair[0]
tool_started{glob} → tool_completed{glob}  → pair[1]
...
```

**第二遍**：遍历所有事件，构建 step 序列

```
assistant_delta + assistant_complete → 累积 message 文本，提取 <thinking>
tool_started  → 创建占位 step（pending）
tool_completed → 补充 pending step 的 observation
```

### reasoning_content 提取

从 `<thinking>...</thinking>` XML 标签内提取思考内容：

```python
import re
thinking_blocks = re.findall(r'<thinking>(.*?)</thinking>', text, re.DOTALL)
reasoning = "\n\n".join(b.strip() for b in thinking_blocks if b.strip())
```

### 工具匹配策略

- 按 `tool_name` 贪心一一配对（第一个未匹配的 tool_started 与下一个 tool_completed 配对）
- tool_started 领先时创建 pending step
- tool_completed 领先时忽略

## 错误处理

| 情况 | 处理 |
|------|------|
| stdout.txt 不存在 | 静默返回，写入 debug 日志 |
| JSON 解析失败 | 跳过该行，写入 debug 日志 |
| tool_started 无对应 tool_completed | 以 output=null 生成 step |
| tool_completed 无对应 tool_started | 忽略 |

## 数据类设计

新增 `benchmarks/trajectory_schema.py`：

```python
@dataclass
class ToolCallStep:
    tool_call_id: str
    function_name: str
    arguments: dict

@dataclass
class ObservationResult:
    source_call_id: str
    content: str | None
    is_error: bool | None

@dataclass
class Observation:
    results: list[ObservationResult]

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
    version: str
    model_name: str | None

@dataclass
class Trajectory:
    schema_version: str
    session_id: str
    agent: Agent
    steps: list[Step]
    final_metrics: FinalMetrics
```

## 文件变更

| 文件 | 操作 |
|------|------|
| `benchmarks/trajectory_schema.py` | 新增：轨迹数据类 |
| `benchmarks/harbor_agent.py` | 修改：实现 `populate_context_post_run()` |

## 验证方式

1. 本地运行一个 build-cython-ext 任务
2. 检查 `run/trajectory.json` 是否生成且格式正确
3. 检查 `run/stdout.txt` 是否完整（无截断）
