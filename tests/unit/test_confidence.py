from tars.genome.confidence import (
    apply_decay,
    compute_confidence,
    decayed_confidence,
    evidence_strength,
    should_deprecate,
)


def test_uninformed_prior() -> None:
    assert compute_confidence(0, 0) == 0.5


def test_all_supporting() -> None:
    conf = compute_confidence(5, 0)
    assert 0.85 < conf < 0.87  # 6/7 ≈ 0.857


def test_all_contradicting() -> None:
    conf = compute_confidence(0, 5)
    assert 0.13 < conf < 0.15  # 1/7 ≈ 0.143


def test_balanced_evidence() -> None:
    assert compute_confidence(3, 3) == 0.5


def test_high_n_vs_low_n_same_ratio() -> None:
    low_n = compute_confidence(2, 0)
    high_n = compute_confidence(20, 0)
    assert high_n > low_n  # more evidence = higher confidence


def test_decay_no_time() -> None:
    s, c = apply_decay(10, 2, days_elapsed=0)
    assert s == 10
    assert c == 2


def test_decay_one_half_life() -> None:
    s, c = apply_decay(10, 2, days_elapsed=90)
    assert abs(s - 5.0) < 0.01
    assert abs(c - 1.0) < 0.01


def test_decay_two_half_lives() -> None:
    s, c = apply_decay(10, 2, days_elapsed=180)
    assert abs(s - 2.5) < 0.01
    assert abs(c - 0.5) < 0.01


def test_decayed_confidence_returns_to_prior() -> None:
    conf = decayed_confidence(10, 2, days_elapsed=365 * 3)
    assert abs(conf - 0.5) < 0.05  # very old evidence ≈ uninformed


def test_evidence_strength_levels() -> None:
    assert evidence_strength(0, 0) == "weak"
    assert evidence_strength(1, 1) == "weak"
    assert evidence_strength(5, 2) == "moderate"
    assert evidence_strength(15, 5) == "strong"
    assert evidence_strength(25, 10) == "robust"


def test_should_deprecate() -> None:
    assert should_deprecate(0.44) is True
    assert should_deprecate(0.45) is False
    assert should_deprecate(0.8) is False
