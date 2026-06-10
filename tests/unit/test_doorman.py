from __future__ import annotations

from datetime import UTC, datetime

from tars.doorman.triggers.cron import CronScheduler, CronTrigger


def test_cron_trigger_valid() -> None:
    t = CronTrigger(expression="*/5 * * * *", task_goal="test")
    assert t.is_valid


def test_cron_trigger_invalid() -> None:
    t = CronTrigger(expression="not a cron", task_goal="test")
    assert not t.is_valid


def test_cron_next_fire() -> None:
    t = CronTrigger(expression="0 * * * *", task_goal="hourly")
    nxt = t.next_fire()
    assert nxt > datetime.now(UTC)


def test_cron_seconds_until_next() -> None:
    t = CronTrigger(expression="*/1 * * * *", task_goal="every min")
    secs = t.seconds_until_next()
    assert 0 <= secs <= 60


def test_cron_scheduler_add() -> None:
    s = CronScheduler()
    s.add_trigger(CronTrigger(expression="*/5 * * * *", task_goal="test"))
    assert s.trigger_count == 1


def test_cron_scheduler_rejects_invalid() -> None:
    s = CronScheduler()
    s.add_trigger(CronTrigger(expression="nope", task_goal="bad"))
    assert s.trigger_count == 0
