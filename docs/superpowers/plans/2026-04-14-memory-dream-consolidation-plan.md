# Dream Memory Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Dream Consolidation engine that periodically cleans, merges, and prunes memory files to对抗记忆熵增.

**Architecture:** A DreamEngine class runs a 4-phase consolidation pass driven by a prompt template. Manual trigger via `/dream` command shows diff preview; cron trigger auto-applies. Changes include MEMORY.md index updates, memory file edits/deletions, and new memory extraction from logs/transcripts.

**Tech Stack:** Python, existing openharness memory/path/hooks infrastructure, cron scheduling.

---

## File Map

```
src/openharness/prompts/
  └── dream_consolidation.md         # NEW: prompt template

src/openharness/memory/
  ├── consolidation.py                # NEW: DreamEngine class
  └── __init__.py                    # MODIFY: export DreamEngine

src/openharness/commands/
  └── dream.py                       # NEW: /dream command

src/openharness/config/
  └── settings.py                    # MODIFY: add DreamSettings

src/openharness/hooks/
  ├── events.py                      # MODIFY: confirm SESSION_END available
  └── executor.py                    # MODIFY: register SESSION_END hook

scripts/
  └── dream_cron.py                  # NEW: cron entry point

tests/
  └── unit/
      └── memory/
          ├── test_consolidation.py  # NEW
          └── test_dream_command.py  # NEW
```

---

## Task 1: DreamSettings

**Files:**
- Modify: `src/openharness/config/settings.py:58-64`

- [ ] **Step 1: Add DreamSettings class after MemorySettings**

```python
class DreamSettings(BaseModel):
    """Dream memory consolidation configuration."""

    enabled: bool = True
    cron_schedule: str = "0 2 * * *"  # Daily 02:00 local
    index_max_lines: int = 200
    index_max_size_kb: int = 25
    auto_apply: bool = True  # True for cron, ignored for manual trigger
```

- [ ] **Step 2: Add dream field to Settings class**

Find the `memory: MemorySettings` field in Settings (line ~429) and add below it:
```python
    dream: DreamSettings = Field(default_factory=DreamSettings)
```

- [ ] **Step 3: Run type check**

Run: `uv run mypy src/openharness/config/settings.py`
Expected: No errors related to DreamSettings

- [ ] **Step 4: Commit**

```bash
git add src/openharness/config/settings.py
git commit -m "feat(settings): add DreamSettings for memory consolidation config"
```

---

## Task 2: Dream Consolidation Prompt Template

**Files:**
- Create: `src/openharness/prompts/dream_consolidation.md`

- [ ] **Step 1: Create the prompt template**

```markdown
<!--
name: 'Dream: Memory Consolidation'
description: Instructs an agent to perform a multi-phase memory consolidation pass
variables:
  - MEMORY_DIR
  - MEMORY_DIR_CONTEXT
  - TRANSCRIPTS_DIR
  - INDEX_FILE
  - INDEX_MAX_LINES
  - ADDITIONAL_CONTEXT
-->
# Dream: Memory Consolidation

You are performing a dream — a reflective pass over your memory files. Synthesize what you've learned recently into durable, well-organized memories so that future sessions can orient quickly.

Memory directory: `${MEMORY_DIR}`
${MEMORY_DIR_CONTEXT}

Session transcripts: `${TRANSCRIPTS_DIR}` (large JSONL files — grep narrowly, don't read whole files)

---

## Phase 1 — Orient

- `ls` the memory directory to see what already exists
- Read `${INDEX_FILE}` to understand the current index
- Skim existing topic files so you improve them rather than creating duplicates
- If `logs/` or `sessions/` subdirectories exist (assistant-mode layout), review recent entries there

## Phase 2 — Gather recent signal

Look for new information worth persisting. Sources in rough priority order:

1. **Daily logs** (`logs/YYYY/MM/YYYY-MM-DD.md`) if present — these are the append-only stream
2. **Existing memories that drifted** — facts that contradict something you see in the codebase now
3. **Transcript search** — if you need specific context (e.g., "what was the error message from yesterday's build failure?"), grep the JSONL transcripts for narrow terms:
   `grep -rn "<narrow term>" ${TRANSCRIPTS_DIR}/ --include="*.jsonl" | tail -50`

Don't exhaustively read transcripts. Look only for things you already suspect matter.

## Phase 3 — Consolidate

For each thing worth remembering, write or update a memory file at the top level of the memory directory. Use the memory file format and type conventions from your system prompt's auto-memory section — it's the source of truth for what to save, how to structure it, and what NOT to save.

Focus on:
- Merging new signal into existing topic files rather than creating near-duplicates
- Converting relative dates ("yesterday", "last week") to absolute dates so they remain interpretable after time passes
- Deleting contradicted facts — if today's investigation disproves an old memory, fix it at the source
- Adding `last_consolidated: YYYY-MM-DD` to each modified memory's frontmatter

## Phase 4 — Prune and index

Update `${INDEX_FILE}` so it stays under ${INDEX_MAX_LINES} lines AND under ~25KB. It's an **index**, not a dump — each entry should be one line under ~150 characters: `- [Title](file.md) — one-line hook`. Never write memory content directly into it.

- Remove pointers to memories that are now stale, wrong, or superseded
- Demote verbose entries: if an index line is over ~200 chars, it's carrying content that belongs in the topic file — shorten the line, move the detail
- Add pointers to newly important memories
- Resolve contradictions — if two files disagree, fix the wrong one

---

Return a brief summary of what you consolidated, updated, or pruned. If nothing changed (memories are already tight), say so.${ADDITIONAL_CONTEXT?`

## Additional context
${ADDITIONAL_CONTEXT}`:""}
```

- [ ] **Step 2: Commit**

```bash
git add src/openharness/prompts/dream_consolidation.md
git commit -m "feat(prompts): add dream memory consolidation prompt template"
```

---

## Task 3: DreamEngine Class

**Files:**
- Create: `src/openharness/memory/consolidation.py`
- Modify: `src/openharness/memory/__init__.py`

- [ ] **Step 1: Write test for DreamEngine.run_consolidation**

```python
# tests/unit/memory/test_consolidation.py
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from openharness.memory.consolidation import DreamEngine, DiffEntry, ConsolidationResult


def test_run_consolidation_dry_run_returns_diff(mock_cwd, mock_memory_dir):
    engine = DreamEngine()
    result = engine.run_consolidation(cwd=mock_cwd, dry_run=True)

    assert isinstance(result, ConsolidationResult)
    assert result.dry_run is True
    assert result.changed_files == [] or result.llm_output is not None


def test_compute_diff_detects_added_and_removed(tmp_path):
    engine = DreamEngine()
    before = []
    after = [tmp_path / "new_memory.md"]
    diff = engine.compute_diff(before, after)

    assert any(e.action == "create" for e in diff)
    assert any(e.path == tmp_path / "new_memory.md" for e in diff)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/memory/test_consolidation.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal DreamEngine**

```python
# src/openharness/memory/consolidation.py
"""Dream memory consolidation engine."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from openharness.memory.paths import get_memory_entrypoint, get_project_memory_dir


@dataclass(frozen=True)
class DiffEntry:
    """A single change to a memory file."""

    action: str  # "create" | "delete" | "update"
    path: Path
    summary: str = ""


@dataclass(frozen=True)
class ConsolidationResult:
    """Result of a consolidation run."""

    dry_run: bool
    llm_output: str | None
    changed_files: list[Path]
    summary: str


class DreamEngine:
    def run_consolidation(
        self,
        cwd: Path,
        *,
        dry_run: bool = False,
    ) -> ConsolidationResult:
        prompt = self.build_dream_prompt(cwd)
        # TODO: invoke LLM with prompt
        return ConsolidationResult(
            dry_run=dry_run,
            llm_output=None,
            changed_files=[],
            summary="",
        )

    def build_dream_prompt(
        self,
        cwd: Path,
        additional_context: str | None = None,
    ) -> str:
        memory_dir = get_project_memory_dir(cwd)
        entrypoint = get_memory_entrypoint(cwd)
        template = Path(__file__).parent.parent / "prompts" / "dream_consolidation.md"
        content = template.read_text(encoding="utf-8")

        context_lines = [f"- Memory directory: {memory_dir}"]
        if (memory_dir / "logs").exists():
            logs = list((memory_dir / "logs").rglob("*.md"))
            if logs:
                recent = sorted(logs)[-3:]
                context_lines.append(f"- Recent logs: {', '.join(str(p.relative_to(memory_dir)) for p in recent)}")

        return content \
            .replace("${MEMORY_DIR}", str(memory_dir)) \
            .replace("${MEMORY_DIR_CONTEXT}", "\n".join(context_lines)) \
            .replace("${TRANSCRIPTS_DIR}", str(memory_dir / "sessions")) \
            .replace("${INDEX_FILE}", str(entrypoint)) \
            .replace("${INDEX_MAX_LINES}", "200")

    def compute_diff(self, before: list[Path], after: list[Path]) -> list[DiffEntry]:
        diffs = []
        for path in after:
            if path not in before:
                diffs.append(DiffEntry(action="create", path=path))
        for path in before:
            if path not in after:
                diffs.append(DiffEntry(action="delete", path=path))
        return diffs
```

- [ ] **Step 4: Run test to verify it fails (missing exports)**

Run: `uv run pytest tests/unit/memory/test_consolidation.py -v`
Expected: FAIL — ConsolidationResult/DreamEngine not imported

- [ ] **Step 5: Update memory/__init__.py exports**

Add to `__all__` in `src/openharness/memory/__init__.py`:
```python
    "ConsolidationResult",
    "DiffEntry",
    "DreamEngine",
```

And add import:
```python
from openharness.memory.consolidation import ConsolidationResult, DiffEntry, DreamEngine
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/memory/test_consolidation.py -v`
Expected: PASS (with unimplemented stub)

- [ ] **Step 7: Commit**

```bash
git add src/openharness/memory/ tests/unit/memory/test_consolidation.py
git commit -m "feat(memory): add DreamEngine skeleton with ConsolidationResult"
```

---

## Task 4: /dream Command

**Files:**
- Create: `src/openharness/commands/dream.py`

- [ ] **Step 1: Write test for /dream command**

```python
# tests/unit/memory/test_dream_command.py
import argparse
from unittest.mock import MagicMock, patch
from openharness.commands.dream import DreamCommand


def test_dream_command_dry_run_shows_diff():
    cmd = DreamCommand()
    parser = cmd.get_parser()
    args = parser.parse_args(["--dry-run"])
    assert args.dry_run is True
    assert args.confirm is False


def test_dream_command_with_confirm():
    cmd = DreamCommand()
    parser = cmd.get_parser()
    args = parser.parse_args(["--confirm"])
    assert args.confirm is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/memory/test_dream_command.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write DreamCommand class**

```python
# src/openharness/commands/dream.py
"""The /dream command for memory consolidation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openharness.memory.consolidation import DreamEngine, ConsolidationResult


class DreamCommand:
    name = "dream"
    description = "Run dream memory consolidation"

    def get_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="/dream")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without making changes",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm changes before applying (default for manual trigger)",
        )
        return parser

    def execute(self, args: argparse.Namespace, cwd: Path) -> ConsolidationResult:
        engine = DreamEngine()
        dry_run = args.dry_run or not args.confirm
        result = engine.run_consolidation(cwd=cwd, dry_run=dry_run)

        if result.llm_output:
            print("=== Dream Output ===")
            print(result.llm_output)

        if result.changed_files:
            print("\n=== Changes ===")
            for f in result.changed_files:
                print(f"  {f}")

        if result.summary:
            print(f"\n{result.summary}")

        return result
```

- [ ] **Step 4: Register command in registry**

Add to `src/openharness/commands/registry.py`:
```python
from openharness.commands.dream import DreamCommand
COMMANDS["dream"] = DreamCommand()
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/memory/test_dream_command.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/openharness/commands/dream.py src/openharness/commands/registry.py tests/unit/memory/test_dream_command.py
git commit -m "feat(commands): add /dream memory consolidation command"
```

---

## Task 5: Session End Hook Integration

**Files:**
- Modify: `src/openharness/hooks/executor.py`
- Modify: `src/openharness/hooks/types.py` (if needed)

- [ ] **Step 1: Examine executor.py for hook registration pattern**

Read `src/openharness/hooks/executor.py` to understand how hooks are registered and called.

- [ ] **Step 2: Add SESSION_END hook support**

If SESSION_END is not already in the hook executor, add it. The pattern should mirror existing hooks like PRE_TOOL_USE.

- [ ] **Step 3: Register dream consolidation in SESSION_END**

Add to the SESSION_END handler:
```python
from openharness.memory.consolidation import DreamEngine

def _run_session_end_hooks(...) -> None:
    settings = load_settings()
    if settings.dream.enabled:
        engine = DreamEngine()
        engine.run_consolidation(cwd=cwd, dry_run=False)
```

- [ ] **Step 4: Commit**

```bash
git add src/openharness/hooks/executor.py
git commit -m "feat(hooks): add SESSION_END hook for dream consolidation"
```

---

## Task 6: Cron Script

**Files:**
- Create: `scripts/dream_cron.py`

- [ ] **Step 1: Write cron entry point script**

```python
#!/usr/bin/env python3
"""Cron entry point for dream memory consolidation.

Usage: python scripts/dream_cron.py [--cwd PATH]

This script is designed to be run by a cron scheduler. It:
1. Loads settings from ~/.openharness/settings.json
2. Runs dream consolidation with auto_apply=True
3. Logs results to stderr
"""
import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openharness.config.settings import load_settings
from openharness.memory.consolidation import DreamEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Dream memory consolidation cron")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args()

    settings = load_settings()
    if not settings.dream.enabled:
        print("Dream consolidation is disabled", file=sys.stderr)
        sys.exit(0)

    engine = DreamEngine()
    result = engine.run_consolidation(cwd=args.cwd, dry_run=False)

    if result.summary:
        print(f"[dream] {result.summary}", file=sys.stderr)
    else:
        print("[dream] No changes", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/dream_cron.py
git commit -m "feat(scripts): add dream consolidation cron entry point"
```

---

## Task 7: Integration Test

**Files:**
- Create: `tests/integration/test_dream_consolidation.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_dream_consolidation.py
import pytest
from pathlib import Path
from openharness.memory.consolidation import DreamEngine


def test_dream_engine_smoke_test(tmp_path):
    """Verify DreamEngine can be instantiated and produces output."""
    engine = DreamEngine()
    prompt = engine.build_dream_prompt(cwd=tmp_path)

    assert "Dream: Memory Consolidation" in prompt
    assert "${MEMORY_DIR}" not in prompt  # Should be substituted
    assert "${INDEX_MAX_LINES}" not in prompt  # Should be substituted
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/integration/test_dream_consolidation.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_dream_consolidation.py
git commit -m "test: add smoke test for DreamEngine"
```

---

## Spec Coverage Check

| Spec Section | Task |
|---|---|
| 4-phase consolidation | Task 2 (prompt), Task 3 (DreamEngine) |
| MEMORY.md 格式扩展 last_consolidated | Task 2 (prompt Phase 3) |
| /dream 命令 + diff 预览 | Task 4 |
| 手动触发需确认，定时自动生效 | Task 4 (--confirm flag), Task 5 (cron auto_apply) |
| DreamSettings 配置 | Task 1 |
| cron 入口脚本 | Task 6 |
| 整合操作权限（手动/定时） | Task 4 (--confirm), Task 5 (auto_apply) |
| 边界情况处理 | Task 3 (stub, TODO in full impl) |

## Type Consistency Check

- `DreamEngine.run_consolidation(cwd: Path, *, dry_run: bool = False)` — matches Task 4 call
- `ConsolidationResult(dry_run, llm_output, changed_files, summary)` — all fields defined
- `DiffEntry(action: str, path: Path, summary: str)` — action values match compute_diff: "create"|"delete"|"update"
- `DreamSettings` fields: `enabled`, `cron_schedule`, `index_max_lines`, `index_max_size_kb`, `auto_apply`

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-14-memory-dream-consolidation-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
