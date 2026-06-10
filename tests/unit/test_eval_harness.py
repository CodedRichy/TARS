from __future__ import annotations

import json
from pathlib import Path

from tars.eval.harness import EvalResult, EvalSummary, EvalTask, load_suite
from tars.genome.models import Outcome


def test_eval_task_defaults() -> None:
    t = EvalTask(goal="test task")
    assert t.domain == ""
    assert t.tags == []
    assert t.expected_outcome == "SUCCESS"


def test_eval_result_lesson_helped() -> None:
    r = EvalResult(
        task=EvalTask(goal="test"),
        with_lessons=Outcome.SUCCESS,
        without_lessons=Outcome.FAILURE,
    )
    assert r.lesson_helped is True


def test_eval_result_lesson_hurt() -> None:
    r = EvalResult(
        task=EvalTask(goal="test"),
        with_lessons=Outcome.FAILURE,
        without_lessons=Outcome.SUCCESS,
    )
    assert r.lesson_helped is False


def test_eval_result_neutral() -> None:
    r = EvalResult(
        task=EvalTask(goal="test"),
        with_lessons=Outcome.SUCCESS,
        without_lessons=Outcome.SUCCESS,
    )
    assert r.lesson_helped is None


def test_eval_summary_lift() -> None:
    s = EvalSummary(
        total=10,
        with_lessons_success=8,
        without_lessons_success=5,
    )
    assert abs(s.lift - 0.3) < 1e-9


def test_eval_summary_render() -> None:
    s = EvalSummary(total=10, with_lessons_success=8, without_lessons_success=5)
    text = s.render_text()
    assert "A/B Eval" in text
    assert "Lift" in text


def test_eval_summary_p_value_no_discordant() -> None:
    s = EvalSummary(total=5)
    assert s.p_value == 1.0


def test_load_suite(tmp_path: Path) -> None:
    suite_data = [
        {"goal": "list files", "domain": "fs"},
        {"goal": "echo hello"},
    ]
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite_data))
    tasks = load_suite(path)
    assert len(tasks) == 2
    assert tasks[0].goal == "list files"
    assert tasks[0].domain == "fs"
    assert tasks[1].domain == ""
