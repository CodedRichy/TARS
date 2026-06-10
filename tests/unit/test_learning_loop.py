from __future__ import annotations

from tars.genome.learning_loop import detect_correction


def test_detect_correction_actually() -> None:
    assert detect_correction("actually, always use https") == "always use https"


def test_detect_correction_no() -> None:
    result = detect_correction("no, never delete without backup")
    assert result == "never delete without backup"


def test_detect_correction_remember() -> None:
    result = detect_correction("remember: PDFs go to papers folder")
    assert result == "pdfs go to papers folder"


def test_detect_correction_from_now_on() -> None:
    result = detect_correction("from now on, use snake_case for filenames")
    assert result == "use snake_case for filenames"


def test_detect_correction_the_rule_is() -> None:
    result = detect_correction("the rule is always lint before commit")
    assert result == "always lint before commit"


def test_detect_correction_you_should() -> None:
    result = detect_correction("you should check permissions first")
    assert result == "check permissions first"


def test_detect_no_correction_normal_text() -> None:
    assert detect_correction("list files in /tmp") is None


def test_detect_no_correction_question() -> None:
    assert detect_correction("what time is it?") is None
