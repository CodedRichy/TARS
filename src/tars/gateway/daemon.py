from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

from tars.core.config import TarsConfig, load_config
from tars.core.db import Database
from tars.core.log import get_logger, setup_logging
from tars.gateway.server import GatewayServer

logger = get_logger("daemon")

DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 9119


class Daemon:
    def __init__(
        self,
        config: TarsConfig | None = None,
        *,
        api_host: str = DEFAULT_API_HOST,
        api_port: int = DEFAULT_API_PORT,
        enable_api: bool = True,
    ) -> None:
        self.config = config or load_config()
        self.api_host = api_host
        self.api_port = api_port
        self.enable_api = enable_api
        self._server: GatewayServer | None = None
        self._db: Database | None = None
        self._running = False
        self._uvicorn_server: object | None = None

    @property
    def pid_path(self) -> Path:
        return self.config.data_dir / "tars.pid"

    @property
    def is_running(self) -> bool:
        return self._running

    def _write_pid(self) -> None:
        self.pid_path.write_text(str(os.getpid()))

    def _remove_pid(self) -> None:
        if self.pid_path.exists():
            self.pid_path.unlink()

    @staticmethod
    def read_pid(config: TarsConfig | None = None) -> int | None:
        config = config or load_config()
        pid_path = config.data_dir / "tars.pid"
        if not pid_path.exists():
            return None
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)
            return pid
        except (ValueError, ProcessLookupError, PermissionError):
            pid_path.unlink(missing_ok=True)
            return None

    async def start(self) -> None:
        if self._running:
            return

        setup_logging()
        logger.info("TARS daemon starting (pid=%d)", os.getpid())

        self._db = Database(self.config.db_path)
        await self._db.connect()
        await self._db.run_migrations(self.config.migrations_dir)

        self._server = GatewayServer(self.config, self._db)
        self._running = True
        self._write_pid()

        logger.info("TARS daemon ready")

    async def stop(self) -> None:
        if not self._running:
            return

        logger.info("TARS daemon stopping")
        self._running = False

        if self._uvicorn_server is not None:
            import uvicorn

            if isinstance(self._uvicorn_server, uvicorn.Server):
                self._uvicorn_server.should_exit = True
            self._uvicorn_server = None

        if self._server:
            self._server.session_manager.kill_all()

        if self._db:
            await self._db.close()
            self._db = None

        self._remove_pid()
        logger.info("TARS daemon stopped")

    @property
    def server(self) -> GatewayServer:
        if not self._server:
            raise RuntimeError("Daemon not started")
        return self._server

    async def _start_api_server(self) -> None:
        import uvicorn

        from tars.gateway.api import create_api

        fastapi_app = create_api(self._server)
        config = uvicorn.Config(
            fastapi_app,
            host=self.api_host,
            port=self.api_port,
            log_level="info",
        )
        uvi_server = uvicorn.Server(config)
        self._uvicorn_server = uvi_server
        logger.info("TARS API at http://%s:%d", self.api_host, self.api_port)
        await uvi_server.serve()

    async def run_forever(self) -> None:
        await self.start()

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        if sys.platform != "win32":
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, stop_event.set)
        else:
            signal.signal(signal.SIGINT, lambda *_: stop_event.set())

        try:
            if self.enable_api:
                api_task = asyncio.create_task(self._start_api_server())
                wait_task = asyncio.create_task(stop_event.wait())
                done, pending = await asyncio.wait(
                    {api_task, wait_task}, return_when=asyncio.FIRST_COMPLETED
                )
                for t in pending:
                    t.cancel()
            else:
                await stop_event.wait()
        finally:
            await self.stop()
