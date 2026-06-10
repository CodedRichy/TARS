from __future__ import annotations

from tars.router.model_router import ModelRouter, Stakes, TaskClass

GATEKEEPER_PROMPT = (
    "You are a gatekeeper for TARS. An event has occurred"
    " that may require action.\n"
    "Decide whether this event is worth waking the"
    " frontier model for.\n\n"
    "Event: {event_description}\n\n"
    "Respond with ONLY a JSON object:\n"
    '{{"worth_waking": true/false, "reason": "brief explanation",'
    ' "suggested_goal": "task description if worth_waking"}}'
)


class Gatekeeper:
    def __init__(self, router: ModelRouter) -> None:
        self.router = router

    async def should_wake(self, event_description: str) -> dict:
        try:
            import json

            response = await self.router.complete(
                messages=[
                    {
                        "role": "user",
                        "content": GATEKEEPER_PROMPT.format(event_description=event_description),
                    },
                ],
                task_class=TaskClass.TRIAGE,
                stakes=Stakes.LOW,
                temperature=0.1,
                max_tokens=256,
            )

            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]

            return json.loads(text)
        except Exception:
            return {"worth_waking": False, "reason": "gatekeeper failed"}
