from __future__ import annotations

import json
from dataclasses import dataclass, field

from tars.router.model_router import ModelRouter, Stakes, TaskClass


@dataclass
class PlanStep:
    index: int
    description: str
    tool: str
    tool_args: dict = field(default_factory=dict)
    requires_permission: str = ""


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    reasoning: str = ""

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def describe(self) -> str:
        lines = [f"Plan for: {self.goal}"]
        if self.reasoning:
            lines.append(f"Reasoning: {self.reasoning}")
        for s in self.steps:
            perm = f" [needs: {s.requires_permission}]" if s.requires_permission else ""
            lines.append(f"  {s.index}. [{s.tool}] {s.description}{perm}")
        return "\n".join(lines)


PLAN_SYSTEM_PROMPT = """\
You are TARS, a task planner. Given a goal and available tools, decompose the goal \
into concrete steps. Each step must specify which tool to use and its arguments.

Available tools: {tools}

Respond with ONLY a JSON object:
{{
  "reasoning": "brief explanation of approach",
  "steps": [
    {{
      "description": "what this step does",
      "tool": "tool_name",
      "tool_args": {{"arg": "value"}},
      "requires_permission": "tool.tool_name"
    }}
  ]
}}"""


class Planner:
    def __init__(self, router: ModelRouter) -> None:
        self.router = router

    async def create_plan(
        self,
        goal: str,
        context: str,
        available_tools: list[str],
    ) -> Plan:
        system = PLAN_SYSTEM_PROMPT.format(tools=", ".join(available_tools))
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{context}\n\nGoal: {goal}"},
        ]

        response = await self.router.complete(
            messages=messages,
            task_class=TaskClass.SIMPLE,
            stakes=Stakes.LOW,
            temperature=0.2,
            max_tokens=2048,
        )

        return _parse_plan(goal, response.content)


def _parse_plan(goal: str, raw: str) -> Plan:
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]

        data = json.loads(text)
        steps = []
        for i, s in enumerate(data.get("steps", [])):
            steps.append(
                PlanStep(
                    index=i + 1,
                    description=s.get("description", ""),
                    tool=s.get("tool", ""),
                    tool_args=s.get("tool_args", {}),
                    requires_permission=s.get("requires_permission", ""),
                )
            )
        return Plan(
            goal=goal,
            steps=steps,
            reasoning=data.get("reasoning", ""),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return Plan(
            goal=goal,
            steps=[
                PlanStep(
                    index=1,
                    description=goal,
                    tool="shell",
                    tool_args={"command": goal},
                    requires_permission="tool.shell",
                )
            ],
            reasoning="Failed to parse LLM plan, falling back to direct execution",
        )
