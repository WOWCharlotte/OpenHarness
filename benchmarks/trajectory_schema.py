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
