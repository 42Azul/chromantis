from __future__ import annotations

from dataclasses import dataclass, replace
import json
from io import BytesIO
import logging
from pathlib import Path
from secrets import token_hex
from typing import Callable

from chromantis.app import ApplicationService, AuthOperationError
from chromantis.bot.formatters import format_search_results, format_years
from chromantis.bot.i18n import DEFAULT_LANGUAGE, language_name, t
from chromantis.db.repository import IndexStats
from chromantis.search.query_parser import QueryParseError, parse_query
from chromantis.search.service import SearchResult, SearchService

logger = logging.getLogger(__name__)

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except ImportError:  # pragma: no cover - optional runtime dependency
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None
    InputMediaPhoto = None
    Update = object
    Application = None
    CallbackQueryHandler = None
    CommandHandler = None
    ContextTypes = None
    MessageHandler = None
    filters = None


@dataclass(frozen=True)
class ButtonSpec:
    label: str
    callback_data: str


@dataclass(frozen=True)
class FolderSummary:
    folder_path: str
    year: int
    shown_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "folder_path": self.folder_path,
            "year": self.year,
            "shown_count": self.shown_count,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "FolderSummary":
        return cls(
            folder_path=str(payload.get("folder_path", "")),
            year=int(payload.get("year", 0)),
            shown_count=int(payload.get("shown_count", 0)),
        )


@dataclass(frozen=True)
class SessionView:
    kind: str
    scope: str
    text: str
    image_paths: tuple[str, ...] = ()
    query: str = ""
    count: int = 1
    folder_path: str | None = None
    year: int | None = None
    sent_paths: tuple[str, ...] = ()
    folder_summaries: tuple[FolderSummary, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "scope": self.scope,
            "text": self.text,
            "image_paths": list(self.image_paths),
            "query": self.query,
            "count": self.count,
            "folder_path": self.folder_path,
            "year": self.year,
            "sent_paths": list(self.sent_paths),
            "folder_summaries": [summary.to_dict() for summary in self.folder_summaries],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SessionView":
        return cls(
            kind=str(payload.get("kind", "text")),
            scope=str(payload.get("scope", "text")),
            text=str(payload.get("text", "")),
            image_paths=tuple(payload.get("image_paths", [])),
            query=str(payload.get("query", "")),
            count=int(payload.get("count", 1)),
            folder_path=payload.get("folder_path"),
            year=payload.get("year"),
            sent_paths=tuple(payload.get("sent_paths", [])),
            folder_summaries=tuple(
                FolderSummary.from_dict(item) for item in payload.get("folder_summaries", [])
            ),
        )


@dataclass(frozen=True)
class ChatSession:
    current: SessionView | None = None
    history: tuple[SessionView, ...] = ()

    def to_json(self) -> str:
        return json.dumps(
            {
                "current": None if self.current is None else self.current.to_dict(),
                "history": [view.to_dict() for view in self.history],
            }
        )

    @classmethod
    def from_json(cls, raw: str | None) -> "ChatSession":
        if not raw:
            return cls()
        payload = json.loads(raw)
        current = payload.get("current")
        history = payload.get("history", [])
        return cls(
            current=None if current is None else SessionView.from_dict(current),
            history=tuple(SessionView.from_dict(item) for item in history),
        )


@dataclass(frozen=True)
class BotReply:
    text: str
    image_paths: tuple[str, ...] = ()
    buttons: tuple[tuple[ButtonSpec, ...], ...] = ()


@dataclass(frozen=True)
class PeopleEdit:
    action: str
    person_id: int | None = None
    nonce: str = ""
    folders: tuple[str, ...] = ()


class TelegramBotService:
    def __init__(
        self,
        app_service: ApplicationService | SearchService,
        chat_allowlist: tuple[int, ...] = (),
        admin_chat_allowlist: tuple[int, ...] = (),
        stats_provider: Callable[[], IndexStats] | None = None,
        access_code: str | None = None,
        auth_checker: Callable[[int], bool] | None = None,
        auth_granter: Callable[..., None] | None = None,
        auth_revoker: Callable[[int], None] | None = None,
        session_loader: Callable[[int], str | None] | None = None,
        session_saver: Callable[[int, str], None] | None = None,
        session_clearer: Callable[[int], None] | None = None,
    ):
        if isinstance(app_service, SearchService):
            self.app_service = ApplicationService(
                app_service.repository,
                access_code=access_code,
                static_viewer_chat_ids=chat_allowlist,
                static_owner_chat_ids=admin_chat_allowlist,
            )
        else:
            self.app_service = app_service
        self.chat_allowlist = chat_allowlist
        self.admin_chat_allowlist = admin_chat_allowlist
        self.stats_provider = stats_provider
        self.access_code = access_code
        self.auth_checker = auth_checker
        self.auth_granter = auth_granter
        self.auth_revoker = auth_revoker
        self.session_loader = session_loader
        self.session_saver = session_saver
        self.session_clearer = session_clearer
        self.people_edits: dict[int, PeopleEdit] = {}

    def _chat_language(self, chat_id: int | None) -> str:
        if chat_id is None:
            return DEFAULT_LANGUAGE
        return self.app_service.get_chat_language(chat_id) or DEFAULT_LANGUAGE

    def _has_language_preference(self, chat_id: int | None) -> bool:
        if chat_id is None:
            return False
        return self.app_service.get_chat_language(chat_id) is not None

    @staticmethod
    def _t(language: str, key: str, **kwargs: object) -> str:
        return t(language, key, **kwargs)

    def _language_picker_reply(self) -> BotReply:
        language = DEFAULT_LANGUAGE
        return BotReply(
            text="\n\n".join(
                [
                    self._t(language, "language_choose_home"),
                    self._t(language, "language_prompt"),
                ]
            ),
            buttons=self._language_buttons(language),
        )

    def _language_buttons(self, language: str) -> tuple[tuple[ButtonSpec, ...], ...]:
        return (
            (
                ButtonSpec(self._t(language, "button_english"), "language:set:en"),
                ButtonSpec(self._t(language, "button_spanish"), "language:set:es"),
            ),
        )

    def _guest_buttons(self, language: str) -> tuple[tuple[ButtonSpec, ...], ...]:
        return (
            (
                ButtonSpec(self._t(language, "button_search_help"), "nav:search_help"),
                ButtonSpec(self._t(language, "button_settings"), "settings:open"),
            ),
            ((ButtonSpec(self._t(language, "button_home"), "nav:home"),)),
        )

    def _home_text(self, language: str) -> str:
        return "\n\n".join(
            [
                self._t(language, "home_title"),
                self._t(language, "home_intro"),
                self._t(language, "home_hint"),
            ]
        )

    def _authorized_onboarding_reply(self, language: str, prefix: str | None = None) -> BotReply:
        blocks = []
        if prefix:
            blocks.append(prefix)
        blocks.append(self._t(language, "authorized_onboarding"))
        return BotReply(text="\n\n".join(blocks), buttons=self._home_buttons(language))

    def _guest_onboarding_reply(self, language: str, prefix: str | None = None) -> BotReply:
        blocks = []
        if prefix:
            blocks.append(prefix)
        blocks.append(self._t(language, "guest_onboarding"))
        return BotReply(text="\n\n".join(blocks), buttons=self._guest_buttons(language))

    def _settings_reply(self, chat_id: int | None) -> BotReply:
        language = self._chat_language(chat_id)
        language_label = language_name(language, language)
        lines = [
            self._t(language, "settings_title"),
            self._t(language, "settings_language", language_name=language_label),
            self._t(language, "settings_hint"),
        ]
        buttons = (
            ((ButtonSpec(self._t(language, "button_change_language"), "settings:language"),)),
            ((ButtonSpec(self._t(language, "button_home"), "nav:home"),)),
        )
        return BotReply(text="\n\n".join(lines), buttons=buttons)

    def _search_help_reply(self, chat_id: int | None) -> BotReply:
        language = self._chat_language(chat_id)
        buttons = self._home_buttons(language) if self._is_authorized(chat_id) else self._guest_buttons(language)
        return BotReply(text=self._t(language, "search_help_text"), buttons=buttons)

    def _clarification_reply(self, chat_id: int | None, clarification: str | None = None) -> BotReply:
        language = self._chat_language(chat_id)
        keys = {"several_years": "clarify_several_years", "folders": "clarify_folders"}
        return BotReply(
            text=self._t(language, keys.get(clarification, "clarify_text")),
            buttons=self._suggestion_buttons(language, chat_id),
        )

    def _suggestion_buttons(
        self,
        language: str,
        chat_id: int | None,
        has_history: bool = False,
    ) -> tuple[tuple[ButtonSpec, ...], ...]:
        rows: list[tuple[ButtonSpec, ...]] = []
        if self._is_authorized(chat_id):
            rows.extend(
                [
                    (
                        ButtonSpec(self._t(language, "button_browse_years"), "nav:years"),
                        ButtonSpec(self._t(language, "button_people"), "nav:people"),
                    ),
                    (
                        ButtonSpec(self._t(language, "button_random_memory"), "nav:random"),
                        ButtonSpec(self._t(language, "button_home"), "nav:home"),
                    ),
                ]
            )
        else:
            rows.extend(self._guest_buttons(language))
        if has_history:
            rows.append((ButtonSpec(self._t(language, "button_back"), "nav:back"),))
        return tuple(rows)

    def handle_command(
        self,
        command_text: str,
        chat_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
    ) -> BotReply:
        if chat_id is not None:
            self.people_edits.pop(chat_id, None)
        authorized = self._is_authorized(chat_id)
        command, _, raw_args = command_text.strip().partition(" ")
        args = raw_args.strip()
        language = self._chat_language(chat_id)
        logger.info("Handling Telegram command=%s args=%r chat_id=%s", command, args, chat_id)

        if command == "/start":
            if not self._has_language_preference(chat_id):
                return self._language_picker_reply()
            if authorized:
                return self._authorized_onboarding_reply(language)
            return self._guest_onboarding_reply(language)
        if command == "/help":
            if not authorized:
                return BotReply(
                    "\n\n".join([self._t(language, "help_guest"), self._t(language, "search_help_text")]),
                    buttons=self._guest_buttons(language),
                )
            return BotReply(
                "\n\n".join([self._t(language, "help_authorized"), self._t(language, "search_help_text")]),
                buttons=self._home_buttons(language),
            )
        if command == "/settings":
            return self._settings_reply(chat_id)
        if command == "/login":
            return self._handle_login(
                args=args,
                chat_id=chat_id,
                username=username,
                first_name=first_name,
                already_authorized=authorized,
            )
        if command == "/logout":
            return self._handle_logout(chat_id=chat_id, authorized=authorized)
        if not authorized:
            logger.warning("Rejected Telegram command from unauthorized chat_id=%s", chat_id)
            return BotReply(self._t(language, "unauthorized"), buttons=self._guest_buttons(language))
        if command == "/whoami":
            return self._whoami_reply(chat_id=chat_id, username=username, first_name=first_name)
        if command == "/stats":
            if self.stats_provider is None:
                return BotReply(self._t(language, "stats_unavailable"))
            stats = self.stats_provider()
            return BotReply(
                self._t(
                    language,
                    "stats_text",
                    folders=stats.folders,
                    images=stats.images,
                    tags=stats.tags,
                )
            )
        if command == "/years":
            return self._handle_years(args, language=language)
        if command == "/invite":
            return self._handle_invite(args, chat_id=chat_id, language=language)
        if command == "/authorized":
            return self._handle_authorized_args(args, chat_id=chat_id, language=language)
        if command == "/people":
            return self._handle_people(command_text=command_text, chat_id=chat_id, language=language)
        if command == "/folders":
            try:
                results = self.app_service.search_folders(args)
            except QueryParseError as exc:
                return BotReply(str(exc))
            self.app_service.remember_search(chat_id, "folders", args, 10)
            if not results:
                return self._empty_reply(self._t(language, "no_results_folders"), chat_id=chat_id)
            return BotReply(format_search_results("folders", results, language=language))
        if command == "/images":
            count, query = self._parse_count_and_query(args, default_count=3)
            try:
                results = self.app_service.search_images(query, limit=count)
            except QueryParseError as exc:
                return BotReply(str(exc))
            self.app_service.remember_search(chat_id, "images", query, count)
            if not results:
                return self._empty_reply(self._t(language, "no_results_images"), chat_id=chat_id)
            view = self._make_image_view(
                results,
                intro_key="intro_showing_images",
                scope="search_images",
                query=query,
                count=count,
                previous_sent_paths=(),
                language=language,
            )
            return self._persist_and_reply(chat_id, view, push_history=True)
        if command == "/random":
            count, query = self._parse_count_and_query(args, default_count=1)
            try:
                results = self.app_service.random_images(query, count=count)
            except QueryParseError as exc:
                return BotReply(str(exc))
            self.app_service.remember_search(chat_id, "random", query, count)
            if not results:
                logger.info("No random image result for args=%r", args)
                return self._empty_reply(self._t(language, "no_results_images"), chat_id=chat_id)
            view = self._make_image_view(
                results,
                intro_key="intro_random_image" if len(results) == 1 else "intro_random_images",
                scope="random_images",
                query=query,
                count=count,
                previous_sent_paths=(),
                language=language,
            )
            return self._persist_and_reply(chat_id, view, push_history=True)
        if command == "/more":
            count, _query = self._parse_count_and_query(args, default_count=3)
            return self._continue_current_scope(chat_id=chat_id, count=count)
        logger.debug("Unknown Telegram command received: %s", command_text)
        return BotReply(self._t(language, "unknown_command"))

    def handle_text_input(
        self,
        text: str,
        chat_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
    ) -> BotReply:
        stripped = text.strip()
        language = self._chat_language(chat_id)
        if not stripped:
            return BotReply(self._t(language, "send_search_prompt"))
        if stripped.startswith("/"):
            return self.handle_command(
                stripped,
                chat_id=chat_id,
                username=username,
                first_name=first_name,
            )
        if not self._is_authorized(chat_id):
            return BotReply(self._t(language, "unauthorized"), buttons=self._guest_buttons(language))
        if chat_id is not None and chat_id in self.people_edits:
            return self._people_edit_text(chat_id, stripped, language)
        interpreted = self.app_service.interpret_text(stripped)
        logger.info(
            "Interpreted text input action=%s query=%r count=%d chat_id=%s",
            interpreted.action,
            interpreted.query,
            interpreted.count,
            chat_id,
        )
        if interpreted.needs_clarification:
            return self._clarification_reply(chat_id, interpreted.clarification)
        if interpreted.action == "years":
            return BotReply(
                format_years(self.app_service.list_years(), language=language),
                buttons=self._home_buttons(language),
            )
        if interpreted.action == "folders":
            command = f"/folders {interpreted.query}".strip()
        elif interpreted.action == "random":
            suffix = f" {interpreted.query}" if interpreted.query else ""
            command = f"/random {interpreted.count}{suffix}"
        else:
            suffix = f" {interpreted.query}" if interpreted.query else ""
            command = f"/images {interpreted.count}{suffix}"
        return self.handle_command(
            command,
            chat_id=chat_id,
            username=username,
            first_name=first_name,
        )

    def handle_callback(
        self,
        callback_data: str,
        chat_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
    ) -> BotReply:
        if chat_id is not None and not callback_data.startswith("people:"):
            self.people_edits.pop(chat_id, None)
        logger.info("Handling callback=%s chat_id=%s", callback_data, chat_id)
        language = self._chat_language(chat_id)

        if callback_data.startswith("language:set:"):
            if chat_id is None:
                return BotReply(self._t(language, "unable_authorize"))
            selected_language = callback_data.rsplit(":", 1)[1]
            self.app_service.set_chat_language(chat_id, selected_language, actor_chat_id=chat_id)
            selected = self._chat_language(chat_id)
            prefix = self._t(
                selected,
                "language_updated",
                language_name=language_name(selected, selected),
            )
            if self._is_authorized(chat_id):
                return self._authorized_onboarding_reply(selected, prefix=prefix)
            return self._guest_onboarding_reply(selected, prefix=prefix)
        if callback_data == "settings:open":
            return self._settings_reply(chat_id)
        if callback_data == "settings:language":
            if chat_id is None:
                return self._language_picker_reply()
            return BotReply(
                text=self._t(language, "language_prompt"),
                buttons=self._language_buttons(language),
            )
        if callback_data == "nav:home":
            if self._is_authorized(chat_id):
                return BotReply(self._home_text(language), buttons=self._home_buttons(language))
            return self._guest_onboarding_reply(language)
        if callback_data == "nav:search_help":
            return self._search_help_reply(chat_id)
        if not self._is_authorized(chat_id):
            return BotReply(self._t(language, "unauthorized"), buttons=self._guest_buttons(language))

        if callback_data.startswith("people:") and chat_id is not None:
            return self._people_callback(chat_id, callback_data.removeprefix("people:"), language)
        if callback_data.startswith("saved:") and chat_id is not None:
            return self._saved_search_callback(chat_id, callback_data.removeprefix("saved:"), language)
        if callback_data == "nav:back":
            return self._handle_back(chat_id=chat_id)
        if callback_data == "nav:more":
            return self._continue_current_scope(chat_id=chat_id, count=None)
        if callback_data == "nav:years":
            return BotReply(
                format_years(self.app_service.list_years(), language=language),
                buttons=self._home_buttons(language),
            )
        if callback_data == "nav:random":
            return self.handle_command("/random", chat_id=chat_id, username=username, first_name=first_name)
        if callback_data == "nav:people":
            return self.handle_command("/people", chat_id=chat_id, username=username, first_name=first_name)
        if callback_data == "nav:folders":
            return self._show_folder_picker(chat_id=chat_id)
        if callback_data.startswith("nav:folder:"):
            return self._show_selected_folder(chat_id=chat_id, callback_data=callback_data)
        if callback_data == "nav:same_folder":
            return self._same_folder(chat_id=chat_id)
        if callback_data == "nav:same_year":
            return self._same_year(chat_id=chat_id)
        if callback_data == "nav:random_similar":
            return self._random_similar(chat_id=chat_id)
        if callback_data == "nav:refine":
            return self._refine(chat_id=chat_id)
        return BotReply(self._t(language, "unknown_action"))

    def _handle_login(
        self,
        args: str,
        chat_id: int | None,
        username: str | None,
        first_name: str | None,
        already_authorized: bool,
    ) -> BotReply:
        language = self._chat_language(chat_id)
        if chat_id is None:
            return BotReply(self._t(language, "unable_authorize"))
        if already_authorized:
            return BotReply(self._t(language, "already_authorized"))
        if not self.access_code:
            return BotReply(self._t(language, "login_disabled"))
        if not args:
            return BotReply(self._t(language, "login_usage"))
        try:
            authorized_chat = self.app_service.authorize_with_code(
                chat_id,
                args,
                username=username,
                first_name=first_name,
            )
        except ValueError as exc:
            logger.warning("Failed login attempt for chat_id=%s", chat_id)
            return BotReply(str(exc))
        logger.info("Authorized chat_id=%s username=%s role=%s", chat_id, username, authorized_chat.role)
        prefix = self._t(language, "login_success_prefix")
        return self._authorized_onboarding_reply(
            language,
            prefix=prefix,
        )

    def _handle_logout(self, chat_id: int | None, authorized: bool) -> BotReply:
        language = self._chat_language(chat_id)
        if chat_id is None:
            return BotReply(self._t(language, "logout_unavailable"))
        if not authorized:
            return BotReply(self._t(language, "logout_not_authorized"))
        principal = self.app_service.resolve_principal(chat_id)
        if principal.auth_mode.startswith("static_"):
            return BotReply(self._t(language, "logout_static"))
        self.app_service.revoke_own_access(chat_id)
        self._clear_session(chat_id)
        logger.info("Revoked authorization for chat_id=%s", chat_id)
        return BotReply(self._t(language, "logout_success"))

    def _whoami_reply(
        self, chat_id: int | None, username: str | None, first_name: str | None
    ) -> BotReply:
        language = self._chat_language(chat_id)
        principal = self.app_service.resolve_principal(
            chat_id,
            username=username,
            first_name=first_name,
        )
        role = self._role_for_chat(chat_id)
        return BotReply(
            self._t(
                language,
                "whoami_template",
                chat_id=chat_id,
                username=principal.username or "-",
                first_name=principal.first_name or "-",
                auth_mode=principal.auth_mode,
                role=role,
                admin=self._t(language, "admin_yes") if self._is_admin(chat_id) else self._t(language, "admin_no"),
            )
        )

    def _handle_years(self, args: str, language: str) -> BotReply:
        if not args:
            return BotReply(format_years(self.app_service.list_years(), language=language))
        try:
            parsed = parse_query(args)
        except QueryParseError as exc:
            return BotReply(str(exc))
        if parsed.keywords or parsed.people or parsed.year_from is None or parsed.year_to is None:
            return BotReply(self._t(language, "years_usage"))
        return BotReply(
            format_years(
                self.app_service.list_years(parsed.year_from, parsed.year_to),
                language=language,
            )
        )

    def _handle_invite(self, args: str, chat_id: int | None, language: str) -> BotReply:
        parts = [part for part in args.split(" ") if part]
        if not parts:
            parts = ["viewer"]
        if parts[0].lower() == "list":
            try:
                invites = self.app_service.list_invites(chat_id)
            except AuthOperationError as exc:
                return BotReply(self._t(language, exc.code))
            if not invites:
                return BotReply(self._t(language, "no_active_invites"))
            lines = [self._t(language, "active_invites")]
            for invite in invites:
                lines.append(
                    self._t(
                        language,
                        "invite_line",
                        code=invite.code,
                        role=invite.role,
                        used_count=invite.used_count,
                        max_uses=invite.max_uses,
                        expires_at=invite.expires_at or "-",
                    )
                )
            return BotReply("\n".join(lines))
        if parts[0].lower() == "revoke":
            if len(parts) != 2:
                return BotReply(self._t(language, "invite_revoke_usage"))
            return self._revoke_invite_reply(parts[1], chat_id, language=language)
        if not self._is_admin(chat_id):
            return BotReply(self._t(language, "invite_requires_admin"))
        role = parts[0].lower()
        ttl_days = 7
        if role not in {"viewer", "admin"}:
            return BotReply(self._t(language, "invite_usage"))
        if len(parts) > 1:
            if not parts[1].isdigit():
                return BotReply(self._t(language, "invite_usage"))
            ttl_days = max(1, min(int(parts[1]), 30))
        try:
            invite = self.app_service.create_invite(role, created_by_chat_id=chat_id, ttl_days=ttl_days)
        except AuthOperationError as exc:
            return BotReply(self._t(language, exc.code))
        except ValueError as exc:
            return BotReply(str(exc))
        return BotReply(
            self._t(
                language,
                "invite_created",
                role=invite.role,
                code=invite.code,
                expires_at=invite.expires_at,
            )
        )

    def _handle_authorized(self, chat_id: int | None) -> BotReply:
        return self._handle_authorized_args("", chat_id, language=self._chat_language(chat_id))

    def _handle_authorized_args(self, args: str, chat_id: int | None, language: str) -> BotReply:
        if not self._is_admin(chat_id):
            return BotReply(self._t(language, "authorized_requires_admin"))
        parts = [part for part in args.split(" ") if part]
        if not parts:
            chats = self.app_service.list_effective_authorized_chats()
            if not chats:
                return BotReply(self._t(language, "no_authorized_chats"))
            lines = [self._t(language, "authorized_header")]
            for chat in chats:
                lines.append(
                    self._t(
                        language,
                        "authorized_line",
                        chat_id=chat.chat_id,
                        role=chat.role,
                        auth_mode=chat.auth_mode,
                        username=chat.username or "-",
                        first_name=chat.first_name or "-",
                    )
                )
            return BotReply("\n".join(lines))
        action = parts[0].lower()
        if action == "role":
            if len(parts) != 3:
                return BotReply(self._t(language, "authorized_role_usage"))
            return self._set_chat_role_reply(parts[1], parts[2], actor_chat_id=chat_id, language=language)
        if action == "revoke":
            if len(parts) != 2:
                return BotReply(self._t(language, "authorized_revoke_usage"))
            return self._revoke_chat_reply(parts[1], actor_chat_id=chat_id, language=language)
        return BotReply(self._t(language, "authorized_usage"))

    def _saved_search_callback(self, chat_id: int, callback: str, language: str) -> BotReply:
        action, _, value = callback.partition(":")
        if not value.isascii() or not value.isdecimal() or len(value) > 18:
            return BotReply(self._t(language, "unknown_action"))
        number = int(value)
        if action in {"recent", "pinned"}:
            return self._saved_searches_reply(chat_id, action, number, language)
        if action == "run":
            search = self.app_service.repository.get_saved_search(chat_id, number)
            if search is None:
                return self._saved_searches_reply(chat_id, "recent", 0, language)
            args = search.query if search.kind == "folders" else f"{search.count} {search.query}"
            return self.handle_command(f"/{search.kind} {args}", chat_id=chat_id)
        if action in {"pin", "unpin"}:
            try:
                self.app_service.set_search_pinned(chat_id, number, action == "pin")
            except AuthOperationError:
                return BotReply(self._t(language, "unauthorized"), buttons=self._guest_buttons(language))
            return self._saved_searches_reply(chat_id, "recent" if action == "pin" else "pinned", 0, language)
        return BotReply(self._t(language, "unknown_action"))

    def _saved_searches_reply(self, chat_id: int, kind: str, page: int, language: str) -> BotReply:
        page = min(page, 100_000)
        searches = self.app_service.repository.list_saved_searches(
            chat_id, pinned_only=kind == "pinned", limit=9, offset=page * 8
        )
        rows = []
        for search in searches[:8]:
            label = self._t(language, f"saved_kind_{search.kind}", query=search.query[:44])
            pin_action = "unpin" if search.pinned else "pin"
            rows.append((
                ButtonSpec(label, f"saved:run:{search.id}"),
                ButtonSpec(self._t(language, f"button_saved_{pin_action}"), f"saved:{pin_action}:{search.id}"),
            ))
        if page:
            rows.append((ButtonSpec(self._t(language, "button_back"), f"saved:{kind}:{page - 1}"),))
        if len(searches) > 8:
            rows.append((ButtonSpec(self._t(language, "button_next"), f"saved:{kind}:{page + 1}"),))
        other = "recent" if kind == "pinned" else "pinned"
        rows.append((
            ButtonSpec(self._t(language, f"button_saved_{other}"), f"saved:{other}:0"),
            ButtonSpec(self._t(language, "button_home"), "nav:home"),
        ))
        text = self._t(language, f"saved_{kind}_title" if searches else f"saved_{kind}_empty")
        return BotReply(text, buttons=tuple(rows))

    def _handle_people(self, command_text: str, chat_id: int | None, language: str) -> BotReply:
        _, _, raw_args = command_text.partition(" ")
        if not raw_args.strip():
            return self._list_people_reply(language, chat_id)

        action, _, remainder = raw_args.strip().partition(" ")
        action, remainder = action.lower(), remainder.strip()
        if action == "show" and remainder:
            return self._show_person_reply(remainder, language, chat_id)
        if action == "show":
            return BotReply(self._t(language, "people_show_usage"))
        if action not in {"add", "alias", "rename", "link", "unlink"}:
            return BotReply(self._t(language, "people_usage"))
        if not self._is_admin(chat_id):
            return BotReply(self._t(language, "people_write_requires_admin"))
        if action == "add":
            if not remainder:
                return BotReply(self._t(language, "people_add_usage"))
            return self._write_person(action, None, remainder, chat_id, language)
        try:
            identifier, value = self._split_pipe_args(
                remainder, self._t(language, f"people_{action}_usage")
            )
        except ValueError as exc:
            return BotReply(str(exc))
        return self._write_person(action, identifier, value, chat_id, language)

    def _write_person(
        self, action: str, identifier: str | int | None,
        value: str, chat_id: int | None, language: str,
    ) -> BotReply:
        try:
            self._require_admin(chat_id)
            if action == "add":
                detail = self.app_service.create_person(value, actor_chat_id=chat_id)
                heading = "person_created"
            else:
                operations = {
                    "alias": (self.app_service.add_person_alias, "person_alias_added"),
                    "rename": (self.app_service.rename_person, "person_renamed"),
                    "link": (self.app_service.link_person_to_folder, "person_linked"),
                    "unlink": (self.app_service.unlink_person_from_folder, "person_unlinked"),
                }
                operation, heading = operations[action]
                assert identifier is not None
                detail = operation(identifier, value, actor_chat_id=chat_id)
        except PermissionError:
            return BotReply(self._t(language, "people_write_requires_admin"))
        except ValueError as exc:
            return BotReply(str(exc))
        return BotReply(
            self._format_person_detail(detail, heading=self._t(language, heading), language=language),
            buttons=self._person_buttons(detail.id, chat_id, language),
        )

    def _people_callback(self, chat_id: int, callback: str, language: str) -> BotReply:
        action, _, value = callback.partition(":")
        if action == "list":
            self.people_edits.pop(chat_id, None)
            if value.isdecimal() and len(value) <= 8:
                return self._list_people_reply(language, chat_id, page=int(value))
        if action == "show":
            self.people_edits.pop(chat_id, None)
            if value.isascii() and value.isdecimal() and len(value) <= 18:
                return self._show_person_reply(int(value), language, chat_id)
        if not self._is_admin(chat_id):
            self.people_edits.pop(chat_id, None)
            return BotReply(self._t(language, "people_write_requires_admin"))
        if action == "add":
            self.people_edits[chat_id] = PeopleEdit("add")
            return self._people_prompt("people_prompt_add", language)
        if action in {"alias", "rename", "link", "unlink"} and value.isascii() and value.isdecimal() and len(value) <= 18:
            person = self.app_service.get_person_detail(int(value))
            if person is None:
                return BotReply(self._t(language, "unknown_person", identifier=value))
            if action == "unlink":
                if not person.folder_paths:
                    return self._show_person_reply(person.id, language, chat_id)
                edit = PeopleEdit(action, person.id, token_hex(4), person.folder_paths)
                self.people_edits[chat_id] = edit
                return self._people_folder_picker(edit, language)
            self.people_edits[chat_id] = PeopleEdit(action, person.id)
            return self._people_prompt(f"people_prompt_{action}", language)
        if action in {"choose", "page"}:
            nonce, _, index = value.partition(":")
            edit = self.people_edits.get(chat_id)
            if edit and edit.nonce and nonce == edit.nonce and index.isdecimal() and len(index) <= 8:
                selection = int(index)
                if action == "page":
                    return self._people_folder_picker(edit, language, page=selection)
                if 0 <= selection < len(edit.folders):
                    reply = self._write_person(edit.action, edit.person_id, edit.folders[selection], chat_id, language)
                    self.people_edits.pop(chat_id, None)
                    return reply
        return BotReply(self._t(language, "unknown_action"))

    def _people_edit_text(self, chat_id: int, text: str, language: str) -> BotReply:
        edit = self.people_edits[chat_id]
        if not self._is_admin(chat_id):
            self.people_edits.pop(chat_id, None)
            return BotReply(self._t(language, "people_write_requires_admin"))
        if edit.action == "unlink":
            return self._people_folder_picker(edit, language)
        if edit.action == "link":
            try:
                results = self.app_service.search_folders(text, limit=40)
            except QueryParseError as exc:
                return self._people_prompt("people_prompt_link", language, prefix=str(exc))
            if not results:
                self.people_edits[chat_id] = replace(edit, nonce="", folders=())
                return self._people_prompt("people_prompt_link", language, prefix=self._t(language, "no_results_folders"))
            edit = replace(edit, nonce=token_hex(4), folders=tuple(item.path for item in results))
            self.people_edits[chat_id] = edit
            return self._people_folder_picker(edit, language)
        reply = self._write_person(edit.action, edit.person_id, text, chat_id, language)
        if reply.buttons:
            self.people_edits.pop(chat_id, None)
            return reply
        return self._people_prompt(f"people_prompt_{edit.action}", language, prefix=reply.text)

    def _people_prompt(self, key: str, language: str, prefix: str = "") -> BotReply:
        buttons = ((ButtonSpec(self._t(language, "button_cancel"), "people:list:0"),),)
        return BotReply("\n\n".join(filter(None, (prefix, self._t(language, key)))), buttons=buttons)

    def _people_folder_picker(self, edit: PeopleEdit, language: str, page: int = 0) -> BotReply:
        start = min(page, (len(edit.folders) - 1) // 8) * 8
        rows = [
            (ButtonSpec(path[:70], f"people:choose:{edit.nonce}:{index}"),)
            for index, path in enumerate(edit.folders[start:start + 8], start)
        ]
        if start:
            rows.append((ButtonSpec(self._t(language, "button_back"), f"people:page:{edit.nonce}:{start // 8 - 1}"),))
        if start + 8 < len(edit.folders):
            rows.append((ButtonSpec(self._t(language, "button_next"), f"people:page:{edit.nonce}:{start // 8 + 1}"),))
        rows.append((ButtonSpec(self._t(language, "button_cancel"), "people:list:0"),))
        return BotReply(self._t(language, "people_choose_folder"), buttons=tuple(rows))

    def _set_chat_role_reply(
        self,
        raw_chat_id: str,
        role: str,
        actor_chat_id: int | None,
        language: str,
    ) -> BotReply:
        if not self._is_owner(actor_chat_id):
            return BotReply(self._t(language, "authorized_role_owner_only"))
        try:
            target_chat_id = int(raw_chat_id)
        except ValueError:
            return BotReply(self._t(language, "authorized_role_usage"))
        try:
            principal = self.app_service.set_chat_role(
                target_chat_id,
                role=role.lower(),
                actor_chat_id=actor_chat_id,
            )
        except AuthOperationError as exc:
            return BotReply(self._t(language, exc.code))
        except ValueError as exc:
            return BotReply(str(exc))
        return BotReply(
            self._t(
                language,
                "chat_role_updated",
                chat_id=principal.chat_id,
                role=principal.role,
                auth_mode=principal.auth_mode,
            )
        )

    def _revoke_chat_reply(
        self,
        raw_chat_id: str,
        actor_chat_id: int | None,
        language: str,
    ) -> BotReply:
        try:
            target_chat_id = int(raw_chat_id)
        except ValueError:
            return BotReply(self._t(language, "authorized_revoke_usage"))
        try:
            self.app_service.revoke_chat_access(target_chat_id, actor_chat_id=actor_chat_id)
        except AuthOperationError as exc:
            return BotReply(self._t(language, exc.code))
        except ValueError as exc:
            return BotReply(str(exc))
        if target_chat_id == actor_chat_id:
            self._clear_session(target_chat_id)
        return BotReply(self._t(language, "chat_access_revoked", chat_id=target_chat_id))

    def _revoke_invite_reply(self, code: str, actor_chat_id: int | None, language: str) -> BotReply:
        try:
            revoked = self.app_service.revoke_invite(code, actor_chat_id=actor_chat_id)
        except AuthOperationError as exc:
            return BotReply(self._t(language, exc.code))
        except ValueError as exc:
            return BotReply(str(exc))
        return BotReply(
            self._t(
                language,
                "invite_revoked",
                role=revoked.role,
                code=revoked.code,
                revoked_at=revoked.revoked_at,
            )
        )

    def _list_people_reply(self, language: str, chat_id: int | None, page: int = 0) -> BotReply:
        people = self.app_service.list_people()
        start = max(0, min(page, (len(people) - 1) // 8)) * 8
        lines = [self._t(language, "curated_people_header" if people else "no_people")]
        rows = []
        for person in people[start:start + 8]:
            lines.append(
                self._t(
                    language,
                    "people_summary_line",
                    display_name=person.display_name,
                    aliases_count=person.aliases_count,
                    folder_count=person.folder_count,
                )
            )
            rows.append((ButtonSpec(person.display_name[:70], f"people:show:{person.id}"),))
        if start:
            rows.append((ButtonSpec(self._t(language, "button_back"), f"people:list:{start // 8 - 1}"),))
        if start + 8 < len(people):
            rows.append((ButtonSpec(self._t(language, "button_next"), f"people:list:{start // 8 + 1}"),))
        if self._is_admin(chat_id):
            rows.append((ButtonSpec(self._t(language, "button_people_add"), "people:add"),))
        rows.append((ButtonSpec(self._t(language, "button_home"), "nav:home"),))
        return BotReply("\n".join(lines), buttons=tuple(rows))

    def _show_person_reply(self, identifier: str | int, language: str, chat_id: int | None) -> BotReply:
        detail = self.app_service.get_person_detail(identifier)
        if detail is None:
            return BotReply(self._t(language, "unknown_person", identifier=identifier))
        return BotReply(
            self._format_person_detail(
                detail, heading=self._t(language, "person_heading"), language=language
            ),
            buttons=self._person_buttons(detail.id, chat_id, language),
        )

    def _person_buttons(
        self, person_id: int, chat_id: int | None, language: str
    ) -> tuple[tuple[ButtonSpec, ...], ...]:
        rows = []
        if self._is_admin(chat_id):
            for actions in (("alias", "rename"), ("link", "unlink")):
                rows.append(tuple(
                    ButtonSpec(self._t(language, f"button_people_{action}"), f"people:{action}:{person_id}")
                    for action in actions
                ))
        rows.append((ButtonSpec(self._t(language, "button_people"), "people:list:0"),))
        return tuple(rows)

    def _continue_current_scope(self, chat_id: int | None, count: int | None) -> BotReply:
        language = self._chat_language(chat_id)
        if chat_id is None:
            return BotReply(self._t(language, "no_active_session"))
        session = self._load_session(chat_id)
        current = session.current
        if current is None:
            return BotReply(self._t(language, "no_previous_image_search"))
        if current.kind != "images":
            return BotReply(self._t(language, "not_image_batch"))
        next_count = current.count if count is None else count
        view = self._continue_from_view(current, count=next_count, language=language)
        if view is None:
            return self._empty_reply(self._t(language, "no_results_more"), chat_id=chat_id)
        return self._persist_and_reply(chat_id, view, push_history=True)

    def _same_folder(self, chat_id: int | None) -> BotReply:
        language = self._chat_language(chat_id)
        if chat_id is None:
            return BotReply(self._t(language, "no_active_session"))
        session = self._load_session(chat_id)
        current = session.current
        if current is None or not current.folder_path:
            return BotReply(self._t(language, "no_folder_context"))
        results = self.app_service.images_in_folder(
            current.folder_path,
            limit=current.count,
            exclude_paths=current.sent_paths,
        )
        if not results:
            return self._empty_reply(
                self._t(language, "no_results_folder", folder_path=current.folder_path),
                chat_id=chat_id,
            )
        view = self._make_image_view(
            results,
            intro_key="intro_same_folder",
            scope="same_folder",
            query="",
            count=current.count,
            previous_sent_paths=(),
            language=language,
        )
        return self._persist_and_reply(chat_id, view, push_history=True)

    def _same_year(self, chat_id: int | None) -> BotReply:
        language = self._chat_language(chat_id)
        if chat_id is None:
            return BotReply(self._t(language, "no_active_session"))
        session = self._load_session(chat_id)
        current = session.current
        if current is None or current.year is None:
            return BotReply(self._t(language, "no_year_context"))
        results = self.app_service.images_in_year(
            current.year,
            limit=current.count,
            exclude_paths=current.sent_paths,
        )
        if not results:
            return self._empty_reply(
                self._t(language, "no_results_year", year=current.year),
                chat_id=chat_id,
            )
        view = self._make_image_view(
            results,
            intro_key="intro_same_year",
            scope="same_year",
            query="",
            count=current.count,
            previous_sent_paths=(),
            language=language,
            intro_kwargs={"year": current.year},
        )
        return self._persist_and_reply(chat_id, view, push_history=True)

    def _random_similar(self, chat_id: int | None) -> BotReply:
        language = self._chat_language(chat_id)
        if chat_id is None:
            return BotReply(self._t(language, "no_active_session"))
        session = self._load_session(chat_id)
        current = session.current
        if current is None or current.folder_path is None or current.year is None:
            return BotReply(self._t(language, "no_similarity_context"))
        results = self.app_service.related_images(
            current.folder_path,
            current.year,
            limit=current.count,
            randomize=True,
            exclude_paths=current.sent_paths,
        )
        if not results:
            return self._empty_reply(self._t(language, "no_results_related"), chat_id=chat_id)
        view = self._make_image_view(
            results,
            intro_key="intro_random_similar",
            scope="related_images",
            query="",
            count=current.count,
            previous_sent_paths=(),
            language=language,
        )
        return self._persist_and_reply(chat_id, view, push_history=True)

    def _refine(self, chat_id: int | None) -> BotReply:
        language = self._chat_language(chat_id)
        if chat_id is None:
            return BotReply(self._t(language, "no_active_session"))
        session = self._load_session(chat_id)
        current = session.current
        if current is None:
            return BotReply(self._t(language, "no_active_session"))
        lines = [self._t(language, "refine_title")]
        if current.query:
            lines.append(
                self._t(
                    language,
                    "refine_more_results",
                    count=min(current.count + 2, 10),
                    query=current.query,
                )
            )
            lines.append(
                self._t(
                    language,
                    "refine_random",
                    count=current.count,
                    query=current.query,
                )
            )
        if current.year is not None:
            lines.append(
                self._t(language, "refine_same_year", count=current.count, year=current.year)
            )
        if current.folder_path:
            lines.append(self._t(language, "refine_continue_folder", count=current.count))
        return BotReply(
            "\n".join(lines),
            buttons=self._build_buttons(
                current,
                has_history=bool(session.history),
                include_more=False,
                language=language,
            ),
        )

    def _show_folder_picker(self, chat_id: int | None) -> BotReply:
        language = self._chat_language(chat_id)
        if chat_id is None:
            return BotReply(self._t(language, "no_active_session"))
        session = self._load_session(chat_id)
        current = session.current
        if current is None or not current.folder_summaries:
            return BotReply(self._t(language, "folder_picker_none"))
        if len(current.folder_summaries) == 1:
            return BotReply(self._t(language, "folder_picker_single"))
        lines = [
            self._t(language, "folder_picker_title"),
            *(f"- {summary.folder_path}: {summary.shown_count}" for summary in current.folder_summaries),
        ]
        picker = SessionView(
            kind="folder_picker",
            scope="folder_picker",
            text="\n".join(lines),
            query=current.query,
            count=current.count,
            sent_paths=current.sent_paths,
            folder_summaries=current.folder_summaries,
        )
        return self._persist_and_reply(chat_id, picker, push_history=True)

    def _show_selected_folder(self, chat_id: int | None, callback_data: str) -> BotReply:
        language = self._chat_language(chat_id)
        if chat_id is None:
            return BotReply(self._t(language, "no_active_session"))
        session = self._load_session(chat_id)
        current = session.current
        if current is None or not current.folder_summaries:
            return BotReply(self._t(language, "folder_picker_none"))
        try:
            folder_index = int(callback_data.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            return BotReply(self._t(language, "invalid_folder_selection"))
        if folder_index < 0 or folder_index >= len(current.folder_summaries):
            return BotReply(self._t(language, "invalid_folder_selection"))
        selected = current.folder_summaries[folder_index]
        results = self.app_service.images_in_folder(
            selected.folder_path,
            limit=current.count,
            exclude_paths=current.sent_paths,
        )
        if not results:
            return self._empty_reply(
                self._t(language, "no_results_folder_more", folder_path=selected.folder_path),
                chat_id=chat_id,
            )
        view = self._make_image_view(
            results,
            intro_key="intro_more_from_folder",
            scope="same_folder",
            query="",
            count=current.count,
            previous_sent_paths=current.sent_paths,
            language=language,
            intro_kwargs={"folder_path": selected.folder_path},
        )
        return self._persist_and_reply(chat_id, view, push_history=True)

    def _handle_back(self, chat_id: int | None) -> BotReply:
        language = self._chat_language(chat_id)
        if chat_id is None:
            return BotReply(self._t(language, "no_previous_state"))
        session = self._load_session(chat_id)
        if not session.history:
            return BotReply(self._t(language, "no_previous_state"))
        previous = session.history[-1]
        restored = ChatSession(current=previous, history=session.history[:-1])
        self._save_session(chat_id, restored)
        return self._reply_from_view(
            previous,
            has_history=bool(restored.history),
            language=language,
        )

    def _continue_from_view(self, current: SessionView, count: int, language: str) -> SessionView | None:
        intros = {
            "search_images": "intro_more_images",
            "random_images": "intro_more_random_images",
            "same_folder": "intro_more_same_folder",
            "same_year": "intro_more_year",
            "related_images": "intro_more_related_images",
        }
        results = self.app_service.images_for_scope(
            current.scope, current.query, count, current.folder_path, current.year, current.sent_paths
        )
        if not results:
            return None
        return self._make_image_view(
            results,
            intros[current.scope],
            current.scope,
            current.query,
            count,
            current.sent_paths,
            language=language,
            intro_kwargs={"year": current.year} if current.scope == "same_year" else None,
        )

    def _make_image_view(
        self,
        results: list[SearchResult],
        intro_key: str,
        scope: str,
        query: str,
        count: int,
        previous_sent_paths: tuple[str, ...],
        language: str,
        intro_kwargs: dict[str, object] | None = None,
    ) -> SessionView:
        primary = results[0]
        folder_summaries = self._folder_summaries(results)
        years = self._unique_years(results)
        reasons = self._unique_reasons(results)
        sent_paths = tuple(dict.fromkeys([*previous_sent_paths, *(result.path for result in results)]))
        intro = self._t(language, intro_key, **(intro_kwargs or {}))
        text = self._build_image_text(intro, results, folder_summaries, years, reasons, language=language)
        return SessionView(
            kind="images",
            scope=scope,
            text=text,
            image_paths=tuple(result.path for result in results),
            query=query,
            count=count,
            folder_path=primary.folder_path if len(folder_summaries) == 1 else None,
            year=years[0] if len(years) == 1 else None,
            sent_paths=sent_paths,
            folder_summaries=folder_summaries,
        )

    def _persist_and_reply(self, chat_id: int | None, view: SessionView, push_history: bool) -> BotReply:
        has_history = False
        language = self._chat_language(chat_id)
        if chat_id is not None:
            session = self._load_session(chat_id)
            history = session.history
            if push_history and session.current is not None:
                history = (*history[-9:], session.current)
            updated = ChatSession(current=view, history=history)
            self._save_session(chat_id, updated)
            has_history = bool(history)
        return self._reply_from_view(view, has_history=has_history, language=language)

    def _reply_from_view(self, view: SessionView, has_history: bool, language: str) -> BotReply:
        return BotReply(
            text=view.text,
            image_paths=view.image_paths,
            buttons=self._build_buttons(view, has_history=has_history, language=language),
        )

    def _empty_reply(self, text: str, chat_id: int | None) -> BotReply:
        language = self._chat_language(chat_id)
        has_history = bool(chat_id is not None and self._load_session(chat_id).history)
        return BotReply(
            text=text,
            buttons=self._suggestion_buttons(language, chat_id, has_history=has_history),
        )

    def _build_buttons(
        self,
        view: SessionView,
        has_history: bool,
        language: str,
        include_more: bool = True,
    ) -> tuple[tuple[ButtonSpec, ...], ...]:
        rows: list[tuple[ButtonSpec, ...]] = []
        if view.kind == "images":
            first_row: list[ButtonSpec] = []
            if include_more:
                first_row.append(ButtonSpec(self._t(language, "button_more"), "nav:more"))
            if len(view.folder_summaries) > 1:
                first_row.append(ButtonSpec(self._t(language, "button_folders"), "nav:folders"))
            elif view.folder_path and view.scope != "same_folder":
                first_row.append(ButtonSpec(self._t(language, "button_same_folder"), "nav:same_folder"))
            if first_row:
                rows.append(tuple(first_row))
            second_row: list[ButtonSpec] = []
            if view.year is not None and view.scope != "same_year":
                second_row.append(ButtonSpec(self._t(language, "button_same_year"), "nav:same_year"))
            if view.folder_path and view.year is not None and view.scope != "related_images":
                second_row.append(ButtonSpec(self._t(language, "button_random_similar"), "nav:random_similar"))
            if second_row:
                rows.append(tuple(second_row))
            third_row = [
                ButtonSpec(self._t(language, "button_refine"), "nav:refine"),
                ButtonSpec(self._t(language, "button_home"), "nav:home"),
            ]
            if has_history:
                third_row.append(ButtonSpec(self._t(language, "button_back"), "nav:back"))
            rows.append(tuple(third_row))
        elif view.kind == "folder_picker":
            for index, summary in enumerate(view.folder_summaries):
                rows.append((ButtonSpec(self._folder_button_label(summary), f"nav:folder:{index}"),))
            rows.append((ButtonSpec(self._t(language, "button_home"), "nav:home"),))
            if has_history:
                rows.append((ButtonSpec(self._t(language, "button_back"), "nav:back"),))
        else:
            rows.extend(self._home_buttons(language))
            if has_history:
                rows.append((ButtonSpec(self._t(language, "button_back"), "nav:back"),))
        return tuple(rows)

    @staticmethod
    def _folder_summaries(results: list[SearchResult]) -> tuple[FolderSummary, ...]:
        grouped: dict[str, FolderSummary] = {}
        for result in results:
            folder_path = result.folder_path or str(Path(result.path).parent)
            existing = grouped.get(folder_path)
            if existing is None:
                grouped[folder_path] = FolderSummary(folder_path=folder_path, year=result.year, shown_count=1)
                continue
            grouped[folder_path] = FolderSummary(
                folder_path=existing.folder_path,
                year=existing.year,
                shown_count=existing.shown_count + 1,
            )
        return tuple(grouped.values())

    @staticmethod
    def _unique_years(results: list[SearchResult]) -> tuple[int, ...]:
        return tuple(dict.fromkeys(result.year for result in results))

    @staticmethod
    def _unique_reasons(results: list[SearchResult]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(result.reason for result in results if result.reason))

    def _build_image_text(
        self,
        intro: str,
        results: list[SearchResult],
        folder_summaries: tuple[FolderSummary, ...],
        years: tuple[int, ...],
        reasons: tuple[str, ...],
        language: str,
    ) -> str:
        lines = [
            self._t(
                language,
                "image_intro",
                intro=intro,
                count=len(results),
            )
        ]
        if len(folder_summaries) == 1:
            lines.append(self._t(language, "image_folder", folder_path=folder_summaries[0].folder_path))
            if years:
                lines.append(self._t(language, "image_year", year=years[0]))
            if reasons:
                key = "image_reason_single" if len(reasons) == 1 else "image_reason_multiple"
                lines.append(self._t(language, key, reasons="; ".join(reasons)))
            return "\n".join(lines)
        lines.append(self._t(language, "image_folders_in_batch", count=len(folder_summaries)))
        lines.extend(f"- {summary.folder_path}: {summary.shown_count}" for summary in folder_summaries)
        if len(years) == 1:
            lines.append(self._t(language, "image_year", year=years[0]))
        elif years:
            lines.append(self._t(language, "image_years", years=", ".join(str(year) for year in years)))
        if reasons:
            lines.append(self._t(language, "image_matches", reasons="; ".join(reasons)))
        lines.append(self._t(language, "image_use_folders"))
        return "\n".join(lines)

    @staticmethod
    def _folder_button_label(summary: FolderSummary) -> str:
        return f"{summary.folder_path} ({summary.shown_count})"

    def _load_session(self, chat_id: int) -> ChatSession:
        if self.session_loader is None:
            return ChatSession()
        return ChatSession.from_json(self.session_loader(chat_id))

    def _save_session(self, chat_id: int, session: ChatSession) -> None:
        if self.session_saver is None:
            return
        self.session_saver(chat_id, session.to_json())

    def _clear_session(self, chat_id: int) -> None:
        if self.session_clearer is None:
            return
        self.session_clearer(chat_id)

    def _is_authorized(self, chat_id: int | None) -> bool:
        return self.app_service.is_authorized_chat(chat_id)

    def _role_for_chat(self, chat_id: int | None) -> str:
        return self.app_service.resolve_principal(chat_id).role

    def _is_admin(self, chat_id: int | None) -> bool:
        return self._role_for_chat(chat_id) in {"owner", "admin"}

    def _is_owner(self, chat_id: int | None) -> bool:
        return self._role_for_chat(chat_id) == "owner"

    def _require_admin(self, chat_id: int | None) -> None:
        if not self._is_admin(chat_id):
            raise PermissionError("Admin access required.")

    @staticmethod
    def _parse_count_and_query(args: str, default_count: int) -> tuple[int, str]:
        stripped = args.strip()
        if not stripped:
            return default_count, ""
        first, _, remainder = stripped.partition(" ")
        if first.isdigit():
            count = max(1, min(int(first), 10))
            return count, remainder.strip()
        return default_count, stripped

    @staticmethod
    def _split_pipe_args(args: str, usage: str) -> tuple[str, str]:
        left, separator, right = args.partition("|")
        if not separator or not left.strip() or not right.strip():
            raise ValueError(usage)
        return left.strip(), right.strip()

    def _format_person_detail(self, detail, heading: str, language: str) -> str:
        lines = [f"{heading}: {detail.display_name}"]
        if detail.aliases:
            lines.append(self._t(language, "person_aliases_label", aliases=", ".join(detail.aliases)))
        else:
            lines.append(self._t(language, "person_aliases_none"))
        if detail.folder_paths:
            lines.append(self._t(language, "person_linked_folders_label"))
            lines.extend(f"- {folder_path}" for folder_path in detail.folder_paths)
        else:
            lines.append(self._t(language, "person_linked_folders_none"))
        return "\n".join(lines)

    def _home_buttons(self, language: str) -> tuple[tuple[ButtonSpec, ...], ...]:
        return (
            (
                ButtonSpec(self._t(language, "button_browse_years"), "nav:years"),
                ButtonSpec(self._t(language, "button_people"), "nav:people"),
            ),
            (
                ButtonSpec(self._t(language, "button_random_memory"), "nav:random"),
                ButtonSpec(self._t(language, "button_search_help"), "nav:search_help"),
            ),
            (
                ButtonSpec(self._t(language, "button_settings"), "settings:open"),
                ButtonSpec(self._t(language, "button_saved_recent"), "saved:recent:0"),
            ),
        )


class TelegramBotApp:
    def __init__(
        self,
        token: str,
        service: TelegramBotService,
        image_fetcher: Callable[[str], bytes] | None = None,
        image_batch_fetcher: Callable[[tuple[str, ...]], tuple[bytes, ...]] | None = None,
    ):
        if Application is None:
            raise RuntimeError("python-telegram-bot is not installed. Install chromantis[telegram].")
        self.token = token
        self.service = service
        self.image_fetcher = image_fetcher
        self.image_batch_fetcher = image_batch_fetcher

    def build(self):
        application = Application.builder().token(self.token).build()
        for command in (
            "start",
            "help",
            "settings",
            "login",
            "logout",
            "years",
            "folders",
            "images",
            "random",
            "more",
            "people",
            "invite",
            "authorized",
            "whoami",
            "stats",
        ):
            application.add_handler(CommandHandler(command, self._handle))
        application.add_handler(
            CallbackQueryHandler(self._handle_callback, pattern=r"^(nav:|settings:|language:)")
        )
        if MessageHandler is not None and filters is not None:
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))
        return application

    async def _handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message_text = update.message.text if update.message else ""
        chat_id = update.effective_chat.id if update.effective_chat else None
        username = update.effective_user.username if update.effective_user else None
        first_name = update.effective_user.first_name if update.effective_user else None
        logger.debug("Received Telegram update message_text=%r chat_id=%s", message_text, chat_id)
        reply = self.service.handle_command(
            message_text,
            chat_id=chat_id,
            username=username,
            first_name=first_name,
        )
        if not update.message:
            return
        await self._send_reply(update.message, reply)

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        chat_id = update.effective_chat.id if update.effective_chat else None
        username = update.effective_user.username if update.effective_user else None
        first_name = update.effective_user.first_name if update.effective_user else None
        reply = self.service.handle_text_input(
            update.message.text or "",
            chat_id=chat_id,
            username=username,
            first_name=first_name,
        )
        await self._send_reply(update.message, reply)

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.callback_query:
            return
        query = update.callback_query
        chat_id = update.effective_chat.id if update.effective_chat else None
        username = update.effective_user.username if update.effective_user else None
        first_name = update.effective_user.first_name if update.effective_user else None
        reply = self.service.handle_callback(
            query.data or "",
            chat_id=chat_id,
            username=username,
            first_name=first_name,
        )
        await query.answer()
        if query.message:
            await self._send_reply(query.message, reply)

    async def _send_reply(self, message, reply: BotReply) -> None:
        markup = self._build_markup(reply.buttons)
        if reply.image_paths:
            logger.debug("Sending Telegram photo reply count=%d", len(reply.image_paths))
            await self._send_images(message, reply, markup)
            return
        logger.debug("Sending Telegram text reply")
        await message.reply_text(reply.text, reply_markup=markup)

    async def _send_images(self, message, reply: BotReply, markup) -> None:
        image_files = self._open_images(reply.image_paths)
        try:
            if len(image_files) == 1:
                await message.reply_photo(photo=image_files[0], caption=reply.text, reply_markup=markup)
                return
            if InputMediaPhoto is None:
                for image_file in image_files:
                    image_file.seek(0)
                    await message.reply_photo(photo=image_file)
                await message.reply_text(reply.text, reply_markup=markup)
                return
            media = []
            for image_file in image_files:
                image_file.seek(0)
                media.append(InputMediaPhoto(media=image_file))
            await message.reply_media_group(media=media)
            await message.reply_text(reply.text, reply_markup=markup)
        finally:
            for image_file in image_files:
                image_file.close()

    @staticmethod
    def _build_markup(buttons: tuple[tuple[ButtonSpec, ...], ...]):
        if not buttons or InlineKeyboardButton is None or InlineKeyboardMarkup is None:
            return None
        keyboard = [
            [InlineKeyboardButton(button.label, callback_data=button.callback_data) for button in row]
            for row in buttons
        ]
        return InlineKeyboardMarkup(keyboard)

    def _open_images(self, image_paths: tuple[str, ...]) -> list[BytesIO]:
        if not image_paths:
            return []
        if len(image_paths) > 1 and self.image_batch_fetcher is not None:
            logger.debug("Fetching %d images via configured image_batch_fetcher", len(image_paths))
            image_payloads = self.image_batch_fetcher(image_paths)
            return [
                self._bytes_to_image_file(path, image_bytes)
                for path, image_bytes in zip(image_paths, image_payloads, strict=True)
            ]
        return [self._open_image(path) for path in image_paths]

    def _open_image(self, image_path: str):
        if self.image_fetcher is not None:
            logger.debug("Fetching image bytes via configured image_fetcher for %s", image_path)
            image_bytes = self.image_fetcher(image_path)
            return self._bytes_to_image_file(image_path, image_bytes)
        logger.debug("Opening local image path %s", image_path)
        return open(image_path, "rb")

    @staticmethod
    def _bytes_to_image_file(image_path: str, image_bytes: bytes) -> BytesIO:
        image_file = BytesIO(image_bytes)
        image_file.name = Path(image_path).name or "image.jpg"
        return image_file
