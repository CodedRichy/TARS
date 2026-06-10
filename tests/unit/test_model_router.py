from tars.router.model_router import (
    Stakes,
    TaskClass,
    Tier,
    pick_tier,
)


def test_triage_low_goes_local() -> None:
    assert pick_tier(TaskClass.TRIAGE, Stakes.LOW) == Tier.LOCAL


def test_simple_medium_goes_cheap() -> None:
    assert pick_tier(TaskClass.SIMPLE, Stakes.MEDIUM) == Tier.CHEAP


def test_complex_high_goes_frontier() -> None:
    assert pick_tier(TaskClass.COMPLEX, Stakes.HIGH) == Tier.FRONTIER


def test_critical_always_frontier() -> None:
    for stakes in Stakes:
        assert pick_tier(TaskClass.CRITICAL, stakes) == Tier.FRONTIER


def test_moderate_low_goes_cheap() -> None:
    assert pick_tier(TaskClass.MODERATE, Stakes.LOW) == Tier.CHEAP


def test_moderate_high_goes_frontier() -> None:
    assert pick_tier(TaskClass.MODERATE, Stakes.HIGH) == Tier.FRONTIER


def test_tier_values() -> None:
    assert Tier.LOCAL.value == "local"
    assert Tier.CHEAP.value == "cheap"
    assert Tier.FRONTIER.value == "frontier"
