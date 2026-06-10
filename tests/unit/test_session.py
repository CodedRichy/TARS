from __future__ import annotations

from tars.gateway.session import Session, SessionManager, SessionStatus


def test_session_defaults() -> None:
    s = Session()
    assert s.status == SessionStatus.IDLE
    assert s.task_count == 0
    assert s.total_cost_inr == 0.0


def test_session_lifecycle() -> None:
    s = Session()
    s.start_task("do something")
    assert s.status == SessionStatus.ACTIVE
    assert s.current_task == "do something"

    s.complete_task(cost_inr=1.5)
    assert s.status == SessionStatus.IDLE
    assert s.current_task is None
    assert s.task_count == 1
    assert s.total_cost_inr == 1.5


def test_session_kill() -> None:
    s = Session()
    s.start_task("working")
    s.kill()
    assert s.status == SessionStatus.KILLED
    assert s.current_task is None


def test_session_manager_create() -> None:
    mgr = SessionManager()
    s = mgr.create(channel="cli")
    assert s.channel == "cli"
    assert mgr.count == 1


def test_session_manager_get() -> None:
    mgr = SessionManager()
    s = mgr.create()
    assert mgr.get(s.id) is s
    assert mgr.get("nonexistent") is None


def test_session_manager_get_active() -> None:
    mgr = SessionManager()
    s1 = mgr.create()
    s2 = mgr.create()
    s2.kill()
    active = mgr.get_active()
    assert len(active) == 1
    assert active[0].id == s1.id


def test_session_manager_kill_all() -> None:
    mgr = SessionManager()
    mgr.create()
    mgr.create()
    count = mgr.kill_all()
    assert count == 2
    assert len(mgr.get_active()) == 0


def test_session_manager_remove() -> None:
    mgr = SessionManager()
    s = mgr.create()
    mgr.remove(s.id)
    assert mgr.count == 0
