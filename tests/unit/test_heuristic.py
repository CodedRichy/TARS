from tars.genome.models import (
    EvidenceDirection,
    Heuristic,
    HeuristicStatus,
    OriginType,
    Scope,
)


def test_heuristic_defaults() -> None:
    h = Heuristic(id="test", statement="do the thing")
    assert h.status == HeuristicStatus.CANDIDATE
    assert h.confidence == 0.5
    assert h.supporting == 0
    assert h.contradicting == 0
    assert h.origin_type == OriginType.EXTRACTED
    assert h.scope.domains == ["*"]


def test_scope_summary_all() -> None:
    s = Scope()
    assert s.summary == "all tasks"


def test_scope_summary_specific() -> None:
    s = Scope(domains=["file-organization"], tags=["pdf"])
    assert "domains=" in s.summary
    assert "tags=" in s.summary


def test_scope_summary_with_conditions() -> None:
    s = Scope(conditions="when sorting downloads")
    assert "when sorting downloads" in s.summary


def test_heuristic_status_values() -> None:
    assert HeuristicStatus.CANDIDATE.value == "CANDIDATE"
    assert HeuristicStatus.ACTIVE.value == "ACTIVE"
    assert HeuristicStatus.DEPRECATED.value == "DEPRECATED"
    assert HeuristicStatus.REVERTED.value == "REVERTED"


def test_evidence_direction_values() -> None:
    assert EvidenceDirection.SUPPORTING.value == "SUPPORTING"
    assert EvidenceDirection.CONTRADICTING.value == "CONTRADICTING"
