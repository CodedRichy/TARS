from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from tars.channels.base import Channel
from tars.core.config import TarsConfig
from tars.core.db import Database
from tars.gateway.server import GatewayServer
from tars.gateway.session import Session
from tars.genome.changelog import ChangelogManager
from tars.genome.learning_loop import LearningLoop, detect_correction
from tars.genome.promotion import PromotionEngine

logger = logging.getLogger("tars.telegram")


class TelegramChannel(Channel):
    def __init__(self, config: TarsConfig, db: Database) -> None:
        self._config = config
        self._db = db
        self._app: Application | None = None
        self._server: GatewayServer | None = None
        self._sessions: dict[int, Session] = {}
        self._pending_permissions: dict[str, dict] = {}

    @property
    def name(self) -> str:
        return "telegram"

    async def send(self, message: str, **kwargs: Any) -> None:
        chat_id = kwargs.get("chat_id")
        if self._app and chat_id:
            await self._app.bot.send_message(chat_id=chat_id, text=message)

    async def receive(self) -> str | None:
        return None

    def _get_or_create_session(self, chat_id: int) -> Session:
        if chat_id not in self._sessions and self._server:
            self._sessions[chat_id] = self._server.session_manager.create(channel="telegram")
        return self._sessions[chat_id]

    async def start(self) -> None:
        token = self._config.telegram.bot_token
        if not token:
            logger.warning("No Telegram bot token configured")
            return

        self._server = GatewayServer(self._config, self._db)

        self._app = Application.builder().token(token).build()
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("brain", self._cmd_brain))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("grant", self._cmd_grant))
        self._app.add_handler(CommandHandler("teach", self._cmd_teach))
        self._app.add_handler(CommandHandler("kill", self._cmd_kill))
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Telegram bot started")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = self._get_or_create_session(update.effective_chat.id)
        await update.message.reply_text(
            f"TARS online. Session {session.id[:12]}.\n\n"
            "Send a task, or use:\n"
            "/brain — view lessons\n"
            "/status — check budget\n"
            "/grant <cap> — grant permission\n"
            "/teach <lesson> — teach me\n"
            "/kill — emergency stop"
        )

    async def _cmd_brain(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._server:
            return
        lessons = await self._server.genome_store.list_heuristics()
        if not lessons:
            await update.message.reply_text("Brain is empty.")
            return
        lines = []
        for h in lessons[:10]:
            lines.append(f"• [{h.status.value}] {h.statement} ({h.confidence:.0%})")
        await update.message.reply_text("\n".join(lines))

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._server:
            return
        budget = await self._server.router.get_budget_status()
        session = self._get_or_create_session(update.effective_chat.id)
        await update.message.reply_text(
            f"Session: {session.id[:12]}\n"
            f"Tasks: {session.task_count}\n"
            f"Budget: ₹{budget.get('spent_inr', 0):.4f} / ₹{budget.get('limit_inr', 50):.2f}"
        )

    async def _cmd_grant(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._server or not context.args:
            await update.message.reply_text("Usage: /grant <capability>")
            return
        cap = " ".join(context.args)
        await self._server.permissions.grant(cap)
        await update.message.reply_text(f"Granted: {cap}")

    async def _cmd_teach(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._server or not context.args:
            await update.message.reply_text("Usage: /teach <lesson>")
            return
        lesson = " ".join(context.args)
        cl = ChangelogManager(self._db)
        promo = PromotionEngine(self._server.genome_store, cl)
        learner = LearningLoop(self._server.genome_store, cl, promo)
        hid = await learner.on_correction(statement=lesson)
        await update.message.reply_text(f"Learned: {lesson}\nID: {hid[:12]}")

    async def _cmd_kill(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._server:
            return
        result = await self._server.kill_switch.trigger("telegram kill")
        await update.message.reply_text(
            f"Kill switch activated.\n"
            f"Sessions killed: {result['killed_sessions']}\n"
            f"Permissions revoked: {result['revoked_permissions']}"
        )

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._server:
            return
        text = update.message.text.strip()
        if not text:
            return

        correction = detect_correction(text)
        if correction:
            cl = ChangelogManager(self._db)
            promo = PromotionEngine(self._server.genome_store, cl)
            learner = LearningLoop(self._server.genome_store, cl, promo)
            hid = await learner.on_correction(statement=correction)
            await update.message.reply_text(f"Learned: {correction}\nID: {hid[:12]}")
            return

        session = self._get_or_create_session(update.effective_chat.id)
        await update.message.reply_text("Planning...")

        result = await self._server.submit_task(session, goal=text)

        lines = []
        for sr in result.step_results:
            icon = "✓" if sr.status.value == "success" else "✗"
            lines.append(f"{icon} [{sr.step.tool}] {sr.step.description}")
            if sr.tool_result and sr.tool_result.output:
                lines.append(f"  {sr.tool_result.output[:300]}")
            if sr.error:
                lines.append(f"  ⚠ {sr.error}")
        lines.append(f"\n{result.summary}")

        await update.message.reply_text("\n".join(lines))

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        data = query.data or ""

        if data.startswith("grant:"):
            cap = data[6:]
            if self._server:
                await self._server.permissions.grant(cap)
                await query.edit_message_text(f"Granted: {cap}")
        elif data == "deny":
            await query.edit_message_text("Permission denied.")
