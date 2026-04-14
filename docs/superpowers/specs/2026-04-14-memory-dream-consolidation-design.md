# Memory Consolidation (Dream) 设计方案

## 背景问题

当前记忆机制存在**熵增问题**：随着时间推移，记忆文件累积，新旧信息互相干扰。当用户多次修改同一偏好（如工具链从 pip 换成 uv 又换成 pip），过时记忆仍存在于文件中，导致 Agent 行为与用户最新指令冲突。

## 目标

在不破坏现有记忆机制的前提下，引入 **Dream Consolidation** 引擎，通过周期性整合对抗熵增：
- 删除矛盾事实
- 裁剪过时 MEMORY.md 条目
- 将新信号合并到现有 topic
- 从日志中提取新记忆

## 架构概览

```
现有系统                              新增
───────────────────────────────       ────────────────────────────────
MEMORY.md + *.md                      DreamEngine
  ↑                                      │
  │                                      ├── run_consolidation()  — 4阶段执行
find_relevant_memories()                ├── build_dream_prompt()   — 渲染 prompt
  ↑                                      ├── compute_diff()        — 生成变更预览
context.py                               └── apply_changes()       — 写入文件

触发层：
  ├── Stop hook     → /dream 命令（需用户确认 diff）
  └── Cron scheduler → 每日自动执行（无确认）
```

## 核心组件

### 1. Dream Consolidation Prompt

位置：`src/openharness/memory/templates/dream_consolidation.md`

基于 `agent-prompt-dream-memory-consolidation.md` 实现，4 阶段：
- **Phase 1 — Orient**: 遍历记忆目录，读取 MEMORY.md 索引，理解现有 topic 文件
- **Phase 2 — Gather Signal**: 从 logs/、transcripts/ 中提取新信号，关注矛盾点
- **Phase 3 — Consolidate**: 合并信号到 topic 文件，删除矛盾事实，将相对日期转绝对日期
- **Phase 4 — Prune & Index**: MEMORY.md 裁剪至 ≤25KB / ≤200 行，移除过时条目

### 2. DreamEngine

位置：`src/openharness/memory/consolidation.py`

```python
class DreamEngine:
    def run_consolidation(
        self,
        cwd: Path,
        dry_run: bool = False,
    ) -> ConsolidationResult: ...

    def build_dream_prompt(
        self,
        cwd: Path,
        additional_context: str | None = None,
    ) -> str: ...

    def compute_diff(self, before: list[Path], after: list[Path]) -> list[DiffEntry]: ...

    def apply_changes(self, diff: list[DiffEntry]) -> None: ...
```

### 3. /dream 命令

位置：`src/openharness/commands/dream.py`

- 解析命令参数（`--dry-run`, `--verbose`）
- 调用 `DreamEngine.run_consolidation(dry_run=True)` 获取 diff
- 展示变更预览（新增/删除/修改的文件列表）
- 用户确认后调用 `apply_changes()`
- 无 `confirm` 参数时直接执行并打印摘要

### 4. 触发机制

#### 手动触发：Stop Hook + /dream 命令
PostToolUse Stop hook 检测用户是否输入了 `/dream`，若是则触发整合流程并要求用户确认 diff。

#### 定时触发：Cron Job
每日某时刻（默认 02:00 local）自动运行，无确认步骤，直接 apply。

### 5. MEMORY.md 格式扩展

新增 `last_consolidated` 字段：

```markdown
---
name: memory_name
description: one-line description used to decide relevance
type: user | feedback | project | reference
last_consolidated: 2026-04-14
---

memory content...
```

## 整合操作权限

| 操作 | 手动触发（/dream） | 定时触发（cron） |
|------|-------------------|-----------------|
| 更新 MEMORY.md 索引 | ✅ | ✅ |
| 删除/修改记忆正文 | ✅ | ✅ |
| 从 logs/transcripts 新增记忆 | ✅ | ✅ |
| 预览 diff 用户确认 | ✅ | ❌（直接生效） |

## 数据流

```
logs/YYYY/MM/YYYY-MM-DD.md     \
sessions/*.jsonl               → DreamEngine → Dream Prompt → LLM
transcripts grep                  ↓                              ↓
现有 *.md 文件                  ConsolidationResult → compute_diff()
                                                         ↓
                                              [手动] 用户确认 → apply_changes()
                                              [定时] 直接 apply_changes()
```

## 文件变更

```
src/openharness/prompts/
  ├── dream_consolidation.md  # 新增：dream consolidation prompt 模板
  └── context.py              # 修改：整合手动触发入口

src/openharness/memory/
  └── consolidation.py        # 新增：DreamEngine 类

src/openharness/commands/
  └── dream.py                  # 新增：/dream 命令

scripts/
  └── dream_cron.py             # 新增：定时整合脚本（供 cron 调用）

hooks/
  └── post_tool.py              # 修改：Stop hook 注册

src/openharness/config/
  └── settings.py               # 修改：新增 DreamSettings（enabled, cron_schedule, auto_apply）
```

## 配置项

```python
class DreamSettings(BaseModel):
    enabled: bool = True
    cron_schedule: str = "0 2 * * *"  # 每日 02:00
    index_max_lines: int = 200
    index_max_size_kb: int = 25
    auto_apply: bool = True  # 定时任务时为 True，手动触发时忽略
```

## 边界情况

- **无 logs/sessions 目录**: Phase 2 跳过，继续后续阶段
- **MEMORY.md 不存在**: 视为空索引，正常创建
- **整合后索引仍超限**: 提示用户手动清理，或在下次整合时优先删除最旧的条目
- **LLM 整合失败**: 返回错误，保留原文件不变，不破坏现有记忆
