from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from tars.core.events import Event
from tars.core.stream import EventStream
from tars.gateway.api_models import (
    BudgetResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    GrantPermissionRequest,
    KillRequest,
    KillResponse,
    LessonResponse,
    PermissionResponse,
    SessionStatusResponse,
    StatusResponse,
    SubmitTaskRequest,
    TaskResponse,
    TeachRequest,
    TeachResponse,
    WSMessage,
)
from tars.gateway.server import GatewayServer

_server: GatewayServer | None = None


def get_server() -> GatewayServer:
    if _server is None:
        raise RuntimeError("Gateway server not initialized")
    return _server


def set_server(server: GatewayServer) -> None:
    global _server
    _server = server


def create_api(server: GatewayServer | None = None) -> FastAPI:
    if server is not None:
        set_server(server)

    app = FastAPI(
        title="TARS API",
        version="0.1.0",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
    )

    # --- Sessions ---

    @app.post("/api/v1/sessions", response_model=CreateSessionResponse)
    async def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
        srv = get_server()
        session = srv.session_manager.create(channel=req.channel)
        return CreateSessionResponse(
            session_id=session.id,
            channel=session.channel,
            started_at=session.started_at,
        )

    @app.get("/api/v1/sessions/{session_id}", response_model=SessionStatusResponse)
    async def get_session(session_id: str) -> SessionStatusResponse:
        srv = get_server()
        session = srv.session_manager.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return SessionStatusResponse(
            id=session.id,
            channel=session.channel,
            status=session.status.value,
            started_at=session.started_at,
            task_count=session.task_count,
            total_cost_inr=session.total_cost_inr,
            current_task=session.current_task,
        )

    # --- Tasks ---

    @app.post("/api/v1/tasks", response_model=TaskResponse)
    async def submit_task(req: SubmitTaskRequest) -> TaskResponse:
        srv = get_server()
        if srv.kill_switch.is_triggered:
            raise HTTPException(status_code=503, detail="Kill switch active")

        session = None
        if req.session_id:
            session = srv.session_manager.get(req.session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
        else:
            session = srv.session_manager.create(channel="api")

        result = await srv.submit_task(
            session, goal=req.goal, domain=req.domain, tags=req.tags or None
        )
        return TaskResponse(
            outcome=result.outcome.value,
            summary=result.summary,
            episode_id=result.episode_id,
            cost_inr=result.total_cost_inr,
        )

    # --- Brain ---

    @app.get("/api/v1/brain/lessons", response_model=list[LessonResponse])
    async def list_lessons(
        status: str | None = None,
        limit: int = 100,
    ) -> list[LessonResponse]:
        srv = get_server()
        from tars.genome.models import HeuristicStatus

        hs = HeuristicStatus(status) if status else None
        lessons = await srv.genome_store.list_heuristics(status=hs, limit=limit)
        return [
            LessonResponse(
                id=h.id,
                statement=h.statement,
                status=h.status.value,
                confidence=h.confidence,
                supporting=h.supporting,
                contradicting=h.contradicting,
                scope_summary=h.scope.summary,
                created_at=h.created_at,
            )
            for h in lessons
        ]

    @app.post("/api/v1/brain/teach", response_model=TeachResponse)
    async def teach_lesson(req: TeachRequest) -> TeachResponse:
        srv = get_server()
        from tars.genome.changelog import ChangelogManager
        from tars.genome.learning_loop import LearningLoop
        from tars.genome.promotion import PromotionEngine

        cl = ChangelogManager(srv.db)
        promo = PromotionEngine(srv.genome_store, cl)
        loop = LearningLoop(srv.genome_store, cl, promo)

        hid = await loop.on_correction(
            statement=req.statement,
            domain=req.domain,
            tags=req.tags or None,
        )
        h = await srv.genome_store.get_heuristic(hid)
        if not h:
            raise HTTPException(status_code=500, detail="Lesson creation failed")
        return TeachResponse(
            heuristic_id=h.id,
            statement=h.statement,
            confidence=h.confidence,
            status=h.status.value,
        )

    # --- Budget ---

    @app.get("/api/v1/budget", response_model=BudgetResponse)
    async def get_budget() -> BudgetResponse:
        srv = get_server()
        status = await srv.router.get_budget_status()
        return BudgetResponse(**status)

    # --- Permissions ---

    @app.post("/api/v1/permissions", response_model=PermissionResponse)
    async def grant_permission(req: GrantPermissionRequest) -> PermissionResponse:
        srv = get_server()
        perm = await srv.permissions.grant(
            capability=req.capability,
            scope=req.scope,
        )
        return PermissionResponse(
            id=str(perm.id),
            capability=perm.capability,
            scope=perm.scope,
        )

    # --- Kill Switch ---

    @app.post("/api/v1/kill", response_model=KillResponse)
    async def trigger_kill(req: KillRequest) -> KillResponse:
        srv = get_server()
        info = await srv.kill_switch.trigger(req.reason)
        return KillResponse(**info)

    # --- Status ---

    @app.get("/api/v1/status", response_model=StatusResponse)
    async def get_status() -> StatusResponse:
        srv = get_server()
        sessions = srv.session_manager.get_active()
        budget = await srv.router.get_budget_status()
        return StatusResponse(
            active_sessions=len(sessions),
            budget=BudgetResponse(**budget),
            kill_switch=srv.kill_switch.is_triggered,
        )

    # --- Improvement Curves ---

    @app.get("/api/v1/curves")
    async def get_curves(
        period: str = "daily",
        limit: int = 30,
        format: str = "json",
    ) -> Any:
        srv = get_server()
        from tars.curves.renderer import CurveRenderer
        from tars.curves.snapshot import SnapshotCollector

        collector = SnapshotCollector(srv.db)
        snapshots = await collector.list_snapshots(period, limit=limit)
        renderer = CurveRenderer(snapshots)

        if format == "svg":
            return StreamingResponse(
                iter([renderer.to_svg()]),
                media_type="image/svg+xml",
            )
        if format == "badge":
            return {"badge_url": renderer.to_badge()}
        return json.loads(renderer.to_json())

    @app.get("/api/v1/badge")
    async def get_badge() -> Any:
        srv = get_server()
        from tars.curves.renderer import CurveRenderer
        from tars.curves.snapshot import SnapshotCollector

        collector = SnapshotCollector(srv.db)
        snapshots = await collector.list_snapshots("weekly", limit=4)
        renderer = CurveRenderer(snapshots)
        return {"badge_url": renderer.to_badge()}

    # --- WebSocket ---

    @app.websocket("/api/v1/ws/{session_id}")
    async def ws_handler(ws: WebSocket, session_id: str) -> None:
        srv = get_server()
        session = srv.session_manager.get(session_id)
        if not session:
            await ws.close(code=4004, reason="Session not found")
            return

        await ws.accept()
        stream = EventStream(srv.event_bus, session_id=session_id)

        async def sender() -> None:
            try:
                async for event in stream:
                    await ws.send_json(_event_to_dict(event))
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass
            finally:
                stream.close()

        async def receiver() -> None:
            try:
                while True:
                    raw = await ws.receive_json()
                    msg = WSMessage(**raw)
                    await _handle_ws_message(srv, session_id, msg)
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass

        sender_task = asyncio.create_task(sender())
        receiver_task = asyncio.create_task(receiver())
        try:
            await asyncio.gather(sender_task, receiver_task)
        except Exception:
            pass
        finally:
            sender_task.cancel()
            receiver_task.cancel()
            stream.close()

    # --- SSE ---

    @app.get("/api/v1/sse/{session_id}")
    async def sse_handler(session_id: str) -> StreamingResponse:
        srv = get_server()
        session = srv.session_manager.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        async def event_generator() -> AsyncGenerator[str, None]:
            stream = EventStream(srv.event_bus, session_id=session_id)
            try:
                async for event in stream:
                    data = json.dumps(_event_to_dict(event))
                    yield f"event: {event.type.value}\ndata: {data}\n\n"
            finally:
                stream.close()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # --- Backward-compat JSON-RPC ---

    @app.post("/api/v1/rpc")
    async def json_rpc(request: dict[str, Any]) -> dict[str, Any]:
        srv = get_server()
        return await srv.handle_rpc(request)

    return app


def _event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "type": event.type.value,
        "data": event.data,
        "session_id": event.session_id,
        "timestamp": event.timestamp.isoformat(),
    }


async def _handle_ws_message(
    srv: GatewayServer, session_id: str, msg: WSMessage,
) -> None:
    from tars.gateway.api_models import WSMessageType

    if msg.type == WSMessageType.CHAT_MESSAGE:
        session = srv.session_manager.get(session_id)
        if session:
            asyncio.create_task(
                srv.submit_task(
                    session,
                    goal=msg.data.get("text", ""),
                    domain=msg.data.get("domain", ""),
                    tags=msg.data.get("tags"),
                )
            )

    elif msg.type == WSMessageType.PERMISSION_GRANT:
        await srv.permissions.grant(
            capability=msg.data.get("capability", ""),
            scope=msg.data.get("scope", "*"),
        )

    elif msg.type == WSMessageType.BRAIN_TEACH:
        from tars.genome.changelog import ChangelogManager
        from tars.genome.learning_loop import LearningLoop
        from tars.genome.promotion import PromotionEngine

        cl = ChangelogManager(srv.db)
        promo = PromotionEngine(srv.genome_store, cl)
        loop = LearningLoop(srv.genome_store, cl, promo)
        await loop.on_correction(
            statement=msg.data.get("statement", ""),
            domain=msg.data.get("domain", ""),
        )

    elif msg.type == WSMessageType.KILL:
        await srv.kill_switch.trigger(msg.data.get("reason", "WebSocket kill"))
