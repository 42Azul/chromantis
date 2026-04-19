from __future__ import annotations

from dataclasses import dataclass
import json
from io import BytesIO
import logging
from pathlib import Path
from typing import Callable

from chromantis.app import ApplicationService
from chromantis.bot.formatters import format_search_results, format_years
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

    def handle_command(
        self,
        command_text: str,
        chat_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
    ) -> BotReply:
        authorized = self._is_authorized(chat_id)
        command, _, raw_args = command_text.strip().partition(" ")
        args = raw_args.strip()
        logger.info("Handling Telegram command=%s args=%r chat_id=%s", command, args, chat_id)

        if command == "/start":
            if authorized:
                return BotReply(
                    "Chromantis is ready. Type a request like 'show me beach photos from 2019' or use the shortcuts below.",
                    buttons=self._home_buttons(),
                )
            return BotReply("Chromantis is locked. Use /login <access-code> to authorize this chat.")
        if command == "/help":
            if not authorized:
                return BotReply("Commands: /login <access-code>, /help")
            return BotReply(
                "Commands: /years, /folders <query>, /images [count] <query>, "
                "/random [count] [query], /more [count], /people, /invite, /authorized, "
                "/whoami, /stats, /logout\n"
                "Admin: /invite list, /invite revoke <code>, /authorized role <chat-id> "
                "<viewer|admin|owner>, /authorized revoke <chat-id>\n"
                "You can also send plain text like 'show me 3 city photos from 2021'."
            )
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
            return BotReply("Unauthorized chat. Use /login <access-code>.")
        if command == "/whoami":
            return self._whoami_reply(chat_id=chat_id, username=username, first_name=first_name)
        if command == "/stats":
            if self.stats_provider is None:
                return BotReply("Stats are not available.")
            stats = self.stats_provider()
            return BotReply(
                f"Indexed folders: {stats.folders}\n"
                f"Indexed images: {stats.images}\n"
                f"Indexed tags: {stats.tags}"
            )
        if command == "/years":
            return self._handle_years(args)
        if command == "/invite":
            return self._handle_invite(args, chat_id=chat_id)
        if command == "/authorized":
            return self._handle_authorized_args(args, chat_id=chat_id)
        if command == "/people":
            return self._handle_people(command_text=command_text, chat_id=chat_id)
        if command == "/folders":
            try:
                results = self.app_service.search_folders(args)
            except QueryParseError as exc:
                return BotReply(str(exc))
            if not results:
                return self._empty_reply("No folders found.", chat_id=chat_id)
            return BotReply(format_search_results("folders", results))
        if command == "/images":
            count, query = self._parse_count_and_query(args, default_count=3)
            try:
                results = self.app_service.search_images(query, limit=count)
            except QueryParseError as exc:
                return BotReply(str(exc))
            if not results:
                return self._empty_reply("No images found.", chat_id=chat_id)
            view = self._make_image_view(
                results,
                intro="Showing images",
                scope="search_images",
                query=query,
                count=count,
                previous_sent_paths=(),
            )
            return self._persist_and_reply(chat_id, view, push_history=True)
        if command == "/random":
            count, query = self._parse_count_and_query(args, default_count=1)
            try:
                results = self.app_service.random_images(query, count=count)
            except QueryParseError as exc:
                return BotReply(str(exc))
            if not results:
                logger.info("No random image result for args=%r", args)
                return self._empty_reply("No images found.", chat_id=chat_id)
            view = self._make_image_view(
                results,
                intro="Random image" if len(results) == 1 else "Random images",
                scope="random_images",
                query=query,
                count=count,
                previous_sent_paths=(),
            )
            return self._persist_and_reply(chat_id, view, push_history=True)
        if command == "/more":
            count, _query = self._parse_count_and_query(args, default_count=3)
            return self._continue_current_scope(chat_id=chat_id, count=count)
        logger.debug("Unknown Telegram command received: %s", command_text)
        return BotReply("Unknown command. Use /help.")

    def handle_text_input(
        self,
        text: str,
        chat_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
    ) -> BotReply:
        stripped = text.strip()
        if not stripped:
            return BotReply("Send a search like 'show me beach photos from 2019'.")
        if stripped.startswith("/"):
            return self.handle_command(
                stripped,
                chat_id=chat_id,
                username=username,
                first_name=first_name,
            )
        if not self._is_authorized(chat_id):
            return BotReply("Unauthorized chat. Use /login <access-code>.")
        interpreted = self.app_service.interpret_text(stripped)
        logger.info(
            "Interpreted text input action=%s query=%r count=%d chat_id=%s",
            interpreted.action,
            interpreted.query,
            interpreted.count,
            chat_id,
        )
        if interpreted.action == "years":
            return BotReply(format_years(self.app_service.list_years()), buttons=self._home_buttons())
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
        logger.info("Handling callback=%s chat_id=%s", callback_data, chat_id)
        if not self._is_authorized(chat_id):
            return BotReply("Unauthorized chat. Use /login <access-code>.")

        if callback_data == "nav:back":
            return self._handle_back(chat_id=chat_id)
        if callback_data == "nav:home":
            return BotReply(
                "Chromantis home. Type a request like 'city photos from 2021' or use these shortcuts.",
                buttons=self._home_buttons(),
            )
        if callback_data == "nav:more":
            return self._continue_current_scope(chat_id=chat_id, count=None)
        if callback_data == "nav:years":
            return BotReply(format_years(self.app_service.list_years()), buttons=self._home_buttons())
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
        return BotReply("Unknown action.")

    def _handle_login(
        self,
        args: str,
        chat_id: int | None,
        username: str | None,
        first_name: str | None,
        already_authorized: bool,
    ) -> BotReply:
        if chat_id is None:
            return BotReply("Unable to authorize this chat.")
        if already_authorized:
            return BotReply("This chat is already authorized.")
        if not self.access_code:
            return BotReply("Login by access code is not enabled.")
        if not args:
            return BotReply("Usage: /login <access-code>")
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
        return BotReply(
            "Chat authorized. Use /help to see available commands.",
            buttons=self._home_buttons(),
        )

    def _handle_logout(self, chat_id: int | None, authorized: bool) -> BotReply:
        if chat_id is None:
            return BotReply("Unable to logout this chat.")
        if not authorized:
            return BotReply("This chat is not authorized.")
        principal = self.app_service.resolve_principal(chat_id)
        if principal.auth_mode.startswith("static_"):
            return BotReply("This chat is authorized by static configuration and cannot be logged out.")
        self.app_service.revoke_own_access(chat_id)
        self._clear_session(chat_id)
        logger.info("Revoked authorization for chat_id=%s", chat_id)
        return BotReply("Chat authorization removed.")

    def _whoami_reply(
        self, chat_id: int | None, username: str | None, first_name: str | None
    ) -> BotReply:
        principal = self.app_service.resolve_principal(
            chat_id,
            username=username,
            first_name=first_name,
        )
        role = self._role_for_chat(chat_id)
        return BotReply(
            f"Chat ID: {chat_id}\n"
            f"Username: {principal.username or '-'}\n"
            f"First name: {principal.first_name or '-'}\n"
            f"Auth mode: {principal.auth_mode}\n"
            f"Role: {role}\n"
            f"Admin: {'yes' if self._is_admin(chat_id) else 'no'}"
        )

    def _handle_years(self, args: str) -> BotReply:
        if not args:
            return BotReply(format_years(self.app_service.list_years()))
        try:
            parsed = parse_query(args)
        except QueryParseError as exc:
            return BotReply(str(exc))
        if parsed.keywords or parsed.people or parsed.year_from is None or parsed.year_to is None:
            return BotReply("Usage: /years or /years 2018-2021")
        return BotReply(format_years(self.app_service.list_years(parsed.year_from, parsed.year_to)))

    def _handle_invite(self, args: str, chat_id: int | None) -> BotReply:
        parts = [part for part in args.split(" ") if part]
        if not parts:
            parts = ["viewer"]
        if parts[0].lower() == "list":
            if not self._is_admin(chat_id):
                return BotReply("Admin privileges are required for /invite list.")
            invites = self.app_service.list_invites(active_only=True)
            if not invites:
                return BotReply("No active invites.")
            lines = ["Active invites:"]
            for invite in invites:
                lines.append(
                    f"- {invite.code}: role={invite.role}, uses={invite.used_count}/{invite.max_uses}, "
                    f"expires={invite.expires_at or '-'}"
                )
            return BotReply("\n".join(lines))
        if parts[0].lower() == "revoke":
            if len(parts) != 2:
                return BotReply("Usage: /invite revoke <code>")
            return self._revoke_invite_reply(parts[1], chat_id)
        if not self._is_admin(chat_id):
            return BotReply("Admin privileges are required for /invite.")
        role = parts[0].lower()
        ttl_days = 7
        if role not in {"viewer", "admin"}:
            return BotReply("Usage: /invite [viewer|admin] [days]")
        if role == "admin" and not self._is_owner(chat_id):
            return BotReply("Only an owner can generate admin invites.")
        if len(parts) > 1:
            if not parts[1].isdigit():
                return BotReply("Usage: /invite [viewer|admin] [days]")
            ttl_days = max(1, min(int(parts[1]), 30))
        invite = self.app_service.create_invite(
            role=role,
            created_by_chat_id=chat_id,
            ttl_days=ttl_days,
        )
        return BotReply(
            f"Invite created.\nRole: {invite.role}\nCode: {invite.code}\nExpires: {invite.expires_at}"
        )

    def _handle_authorized(self, chat_id: int | None) -> BotReply:
        return self._handle_authorized_args("", chat_id)

    def _handle_authorized_args(self, args: str, chat_id: int | None) -> BotReply:
        if not self._is_admin(chat_id):
            return BotReply("Admin privileges are required for /authorized.")
        parts = [part for part in args.split(" ") if part]
        if not parts:
            chats = self.app_service.list_effective_authorized_chats()
            if not chats:
                return BotReply("No authorized chats.")
            lines = ["Authorized chats:"]
            for chat in chats:
                lines.append(
                    f"- {chat.chat_id}: role={chat.role}, auth_mode={chat.auth_mode}, "
                    f"username={chat.username or '-'}, first_name={chat.first_name or '-'}"
                )
            return BotReply("\n".join(lines))
        action = parts[0].lower()
        if action == "role":
            if len(parts) != 3:
                return BotReply("Usage: /authorized role <chat-id> <viewer|admin|owner>")
            return self._set_chat_role_reply(parts[1], parts[2], actor_chat_id=chat_id)
        if action == "revoke":
            if len(parts) != 2:
                return BotReply("Usage: /authorized revoke <chat-id>")
            return self._revoke_chat_reply(parts[1], actor_chat_id=chat_id)
        return BotReply("Usage: /authorized, /authorized role <chat-id> <viewer|admin|owner>, /authorized revoke <chat-id>")

    def _handle_people(self, command_text: str, chat_id: int | None) -> BotReply:
        _, _, raw_args = command_text.partition(" ")
        args = raw_args.strip()
        if not args:
            return self._list_people_reply()

        action, _, remainder = args.partition(" ")
        action = action.strip().lower()
        remainder = remainder.strip()
        try:
            if action == "show":
                if not remainder:
                    return BotReply("Usage: /people show <name-or-alias>")
                return self._show_person_reply(remainder)
            if action == "add":
                self._require_admin(chat_id)
                if not remainder:
                    return BotReply("Usage: /people add <display-name>")
                detail = self.app_service.create_person(remainder, actor_chat_id=chat_id)
                return BotReply(self._format_person_detail(detail, heading="Person created"))
            if action == "alias":
                self._require_admin(chat_id)
                left, right = self._split_pipe_args(remainder, "Usage: /people alias <canonical> | <alias>")
                detail = self.app_service.add_person_alias(left, right, actor_chat_id=chat_id)
                return BotReply(self._format_person_detail(detail, heading="Alias added"))
            if action == "rename":
                self._require_admin(chat_id)
                left, right = self._split_pipe_args(remainder, "Usage: /people rename <canonical> | <new-display-name>")
                detail = self.app_service.rename_person(left, right, actor_chat_id=chat_id)
                return BotReply(self._format_person_detail(detail, heading="Person renamed"))
            if action == "link":
                self._require_admin(chat_id)
                left, right = self._split_pipe_args(remainder, "Usage: /people link <canonical> | <folder-path>")
                detail = self.app_service.link_person_to_folder(left, right, actor_chat_id=chat_id)
                return BotReply(self._format_person_detail(detail, heading="Person linked"))
            if action == "unlink":
                self._require_admin(chat_id)
                left, right = self._split_pipe_args(remainder, "Usage: /people unlink <canonical> | <folder-path>")
                detail = self.app_service.unlink_person_from_folder(left, right, actor_chat_id=chat_id)
                return BotReply(self._format_person_detail(detail, heading="Person unlinked"))
        except QueryParseError as exc:
            return BotReply(str(exc))
        except PermissionError:
            return BotReply("Admin privileges are required for /people write commands.")
        except ValueError as exc:
            return BotReply(str(exc))
        return BotReply(
            "Usage: /people, /people show <name>, /people add <display-name>, "
            "/people alias <canonical> | <alias>, /people rename <canonical> | <new>, "
            "/people link <canonical> | <folder-path>, /people unlink <canonical> | <folder-path>"
        )

    def _set_chat_role_reply(self, raw_chat_id: str, role: str, actor_chat_id: int | None) -> BotReply:
        if not self._is_owner(actor_chat_id):
            return BotReply("Owner privileges are required for /authorized role.")
        try:
            target_chat_id = int(raw_chat_id)
        except ValueError:
            return BotReply("Usage: /authorized role <chat-id> <viewer|admin|owner>")
        try:
            principal = self.app_service.set_chat_role(
                target_chat_id,
                role=role.lower(),
                actor_chat_id=actor_chat_id,
            )
        except ValueError as exc:
            return BotReply(str(exc))
        return BotReply(
            f"Chat role updated.\nChat ID: {principal.chat_id}\nRole: {principal.role}\nAuth mode: {principal.auth_mode}"
        )

    def _revoke_chat_reply(self, raw_chat_id: str, actor_chat_id: int | None) -> BotReply:
        try:
            target_chat_id = int(raw_chat_id)
        except ValueError:
            return BotReply("Usage: /authorized revoke <chat-id>")
        target = self.app_service.resolve_principal(target_chat_id)
        if target.role == "none":
            return BotReply("Chat is not authorized.")
        if target.auth_mode.startswith("static_"):
            return BotReply("Static chats cannot be revoked.")
        if target.role in {"admin", "owner"} and not self._is_owner(actor_chat_id):
            return BotReply("Owner privileges are required to revoke admin access.")
        if target.role == "viewer" and not self._is_admin(actor_chat_id):
            return BotReply("Admin privileges are required for /authorized revoke.")
        try:
            self.app_service.revoke_chat_access(
                target_chat_id,
                actor_chat_id=actor_chat_id,
                reason="admin_revoke",
            )
        except ValueError as exc:
            return BotReply(str(exc))
        if target_chat_id == actor_chat_id:
            self._clear_session(target_chat_id)
        return BotReply(f"Chat access revoked for {target_chat_id}.")

    def _revoke_invite_reply(self, code: str, actor_chat_id: int | None) -> BotReply:
        invites = {
            invite.code: invite
            for invite in self.app_service.list_invites(active_only=True)
        }
        invite = invites.get(code.strip())
        if invite is None:
            return BotReply("Unknown invite code.")
        if invite.role == "admin" and not self._is_owner(actor_chat_id):
            return BotReply("Owner privileges are required to revoke admin invites.")
        if invite.role == "viewer" and not self._is_admin(actor_chat_id):
            return BotReply("Admin privileges are required for /invite revoke.")
        try:
            revoked = self.app_service.revoke_invite(code, actor_chat_id=actor_chat_id)
        except ValueError as exc:
            return BotReply(str(exc))
        return BotReply(
            f"Invite revoked.\nRole: {revoked.role}\nCode: {revoked.code}\nRevoked: {revoked.revoked_at}"
        )

    def _list_people_reply(self) -> BotReply:
        people = self.app_service.list_people()
        if not people:
            return BotReply("No curated people yet.")
        lines = ["Curated people:"]
        for person in people:
            lines.append(
                f"- {person.display_name}: {person.aliases_count} alias(es), {person.folder_count} folder link(s)"
            )
        return BotReply("\n".join(lines))

    def _show_person_reply(self, identifier: str) -> BotReply:
        detail = self.app_service.get_person_detail(identifier)
        if detail is None:
            return BotReply(f"Unknown person: {identifier}")
        return BotReply(self._format_person_detail(detail, heading="Person"))

    def _continue_current_scope(self, chat_id: int | None, count: int | None) -> BotReply:
        if chat_id is None:
            return BotReply("No active browsing session.")
        session = self._load_session(chat_id)
        current = session.current
        if current is None:
            return BotReply("No previous image search in this chat. Use /images or /random first.")
        if current.kind != "images":
            return BotReply("Current view is not an image batch. Pick a folder or use Back first.")
        next_count = current.count if count is None else count
        view = self._continue_from_view(current, count=next_count)
        if view is None:
            return self._empty_reply("No more images found in the current scope.", chat_id=chat_id)
        return self._persist_and_reply(chat_id, view, push_history=True)

    def _same_folder(self, chat_id: int | None) -> BotReply:
        if chat_id is None:
            return BotReply("No active browsing session.")
        session = self._load_session(chat_id)
        current = session.current
        if current is None or not current.folder_path:
            return BotReply("No folder context available.")
        results = self.app_service.images_in_folder(
            current.folder_path,
            limit=current.count,
            exclude_paths=current.sent_paths,
        )
        if not results:
            return self._empty_reply(f"No images found in folder {current.folder_path}.", chat_id=chat_id)
        view = self._make_image_view(
            results,
            intro="Same folder",
            scope="same_folder",
            query="",
            count=current.count,
            previous_sent_paths=(),
        )
        return self._persist_and_reply(chat_id, view, push_history=True)

    def _same_year(self, chat_id: int | None) -> BotReply:
        if chat_id is None:
            return BotReply("No active browsing session.")
        session = self._load_session(chat_id)
        current = session.current
        if current is None or current.year is None:
            return BotReply("No year context available.")
        results = self.app_service.images_in_year(
            current.year,
            limit=current.count,
            exclude_paths=current.sent_paths,
        )
        if not results:
            return self._empty_reply(f"No images found for year {current.year}.", chat_id=chat_id)
        view = self._make_image_view(
            results,
            intro=f"Same year {current.year}",
            scope="same_year",
            query="",
            count=current.count,
            previous_sent_paths=(),
        )
        return self._persist_and_reply(chat_id, view, push_history=True)

    def _random_similar(self, chat_id: int | None) -> BotReply:
        if chat_id is None:
            return BotReply("No active browsing session.")
        session = self._load_session(chat_id)
        current = session.current
        if current is None or current.folder_path is None or current.year is None:
            return BotReply("No similarity context available.")
        results = self.app_service.related_images(
            current.folder_path,
            current.year,
            limit=current.count,
            randomize=True,
            exclude_paths=current.sent_paths,
        )
        if not results:
            return self._empty_reply("No related images found.", chat_id=chat_id)
        view = self._make_image_view(
            results,
            intro="Random similar",
            scope="related_images",
            query="",
            count=current.count,
            previous_sent_paths=(),
        )
        return self._persist_and_reply(chat_id, view, push_history=True)

    def _refine(self, chat_id: int | None) -> BotReply:
        if chat_id is None:
            return BotReply("No active browsing session.")
        session = self._load_session(chat_id)
        current = session.current
        if current is None:
            return BotReply("No active browsing session.")
        lines = ["Refine this search:"]
        if current.query:
            lines.append(f"- Repeat with more results: /images {min(current.count + 2, 10)} {current.query}")
            lines.append(f"- Random from the same query: /random {current.count} {current.query}")
        if current.year is not None:
            lines.append(f"- Same year only: /images {current.count} {current.year}")
        if current.folder_path:
            lines.append(f"- Continue in folder: /more {current.count}")
        return BotReply(
            "\n".join(lines),
            buttons=self._build_buttons(current, has_history=bool(session.history), include_more=False),
        )

    def _show_folder_picker(self, chat_id: int | None) -> BotReply:
        if chat_id is None:
            return BotReply("No active browsing session.")
        session = self._load_session(chat_id)
        current = session.current
        if current is None or not current.folder_summaries:
            return BotReply("No folder choices available.")
        if len(current.folder_summaries) == 1:
            return BotReply("This batch only contains one folder.")
        lines = [
            "Choose a folder from this batch:",
            *(f"- {summary.folder_path}: {summary.shown_count} shown" for summary in current.folder_summaries),
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
        if chat_id is None:
            return BotReply("No active browsing session.")
        session = self._load_session(chat_id)
        current = session.current
        if current is None or not current.folder_summaries:
            return BotReply("No folder choices available.")
        try:
            folder_index = int(callback_data.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            return BotReply("Invalid folder selection.")
        if folder_index < 0 or folder_index >= len(current.folder_summaries):
            return BotReply("Invalid folder selection.")
        selected = current.folder_summaries[folder_index]
        results = self.app_service.images_in_folder(
            selected.folder_path,
            limit=current.count,
            exclude_paths=current.sent_paths,
        )
        if not results:
            return self._empty_reply(
                f"No more images found in folder {selected.folder_path}.",
                chat_id=chat_id,
            )
        view = self._make_image_view(
            results,
            intro=f"More from {selected.folder_path}",
            scope="same_folder",
            query="",
            count=current.count,
            previous_sent_paths=current.sent_paths,
        )
        return self._persist_and_reply(chat_id, view, push_history=True)

    def _handle_back(self, chat_id: int | None) -> BotReply:
        if chat_id is None:
            return BotReply("No previous state.")
        session = self._load_session(chat_id)
        if not session.history:
            return BotReply("No previous state.")
        previous = session.history[-1]
        restored = ChatSession(current=previous, history=session.history[:-1])
        self._save_session(chat_id, restored)
        return self._reply_from_view(previous, has_history=bool(restored.history))

    def _continue_from_view(self, current: SessionView, count: int) -> SessionView | None:
        if current.scope == "search_images":
            results = self.app_service.search_images(
                current.query,
                limit=count,
                exclude_paths=current.sent_paths,
            )
            if not results:
                return None
            return self._make_image_view(results, "More images", current.scope, current.query, count, current.sent_paths)
        if current.scope == "random_images":
            results = self.app_service.random_images(
                current.query,
                count=count,
                exclude_paths=current.sent_paths,
            )
            if not results:
                return None
            return self._make_image_view(results, "More random images", current.scope, current.query, count, current.sent_paths)
        if current.scope == "same_folder":
            if not current.folder_path:
                return None
            results = self.app_service.images_in_folder(
                current.folder_path,
                limit=count,
                exclude_paths=current.sent_paths,
            )
            if not results:
                return None
            return self._make_image_view(results, "More from the same folder", current.scope, "", count, current.sent_paths)
        if current.scope == "same_year":
            if current.year is None:
                return None
            results = self.app_service.images_in_year(
                current.year,
                limit=count,
                exclude_paths=current.sent_paths,
            )
            if not results:
                return None
            return self._make_image_view(results, f"More from year {current.year}", current.scope, "", count, current.sent_paths)
        if current.scope == "related_images":
            if current.folder_path is None or current.year is None:
                return None
            results = self.app_service.related_images(
                current.folder_path,
                current.year,
                limit=count,
                exclude_paths=current.sent_paths,
                randomize=True,
            )
            if not results:
                return None
            return self._make_image_view(results, "More related images", current.scope, "", count, current.sent_paths)
        return None

    def _make_image_view(
        self,
        results: list[SearchResult],
        intro: str,
        scope: str,
        query: str,
        count: int,
        previous_sent_paths: tuple[str, ...],
    ) -> SessionView:
        primary = results[0]
        folder_summaries = self._folder_summaries(results)
        years = self._unique_years(results)
        reasons = self._unique_reasons(results)
        sent_paths = tuple(dict.fromkeys([*previous_sent_paths, *(result.path for result in results)]))
        text = self._build_image_text(intro, results, folder_summaries, years, reasons)
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
        if chat_id is not None:
            session = self._load_session(chat_id)
            history = session.history
            if push_history and session.current is not None:
                history = (*history[-9:], session.current)
            updated = ChatSession(current=view, history=history)
            self._save_session(chat_id, updated)
            has_history = bool(history)
        return self._reply_from_view(view, has_history=has_history)

    def _reply_from_view(self, view: SessionView, has_history: bool) -> BotReply:
        return BotReply(
            text=view.text,
            image_paths=view.image_paths,
            buttons=self._build_buttons(view, has_history=has_history),
        )

    def _empty_reply(self, text: str, chat_id: int | None) -> BotReply:
        has_history = bool(chat_id is not None and self._load_session(chat_id).history)
        buttons = ((ButtonSpec("Years", "nav:years"), ButtonSpec("Home", "nav:home")),)
        if has_history:
            buttons += ((ButtonSpec("Back", "nav:back"),),)
        return BotReply(text=text, buttons=buttons)

    def _build_buttons(
        self,
        view: SessionView,
        has_history: bool,
        include_more: bool = True,
    ) -> tuple[tuple[ButtonSpec, ...], ...]:
        rows: list[tuple[ButtonSpec, ...]] = []
        if view.kind == "images":
            first_row: list[ButtonSpec] = []
            if include_more:
                first_row.append(ButtonSpec("More", "nav:more"))
            if len(view.folder_summaries) > 1:
                first_row.append(ButtonSpec("Folders", "nav:folders"))
            elif view.folder_path and view.scope != "same_folder":
                first_row.append(ButtonSpec("Same Folder", "nav:same_folder"))
            if first_row:
                rows.append(tuple(first_row))
            second_row: list[ButtonSpec] = []
            if view.year is not None and view.scope != "same_year":
                second_row.append(ButtonSpec("Same Year", "nav:same_year"))
            if view.folder_path and view.year is not None and view.scope != "related_images":
                second_row.append(ButtonSpec("Random Similar", "nav:random_similar"))
            if second_row:
                rows.append(tuple(second_row))
            third_row = [ButtonSpec("Refine", "nav:refine"), ButtonSpec("Home", "nav:home")]
            if has_history:
                third_row.append(ButtonSpec("Back", "nav:back"))
            rows.append(tuple(third_row))
        elif view.kind == "folder_picker":
            for index, summary in enumerate(view.folder_summaries):
                rows.append((ButtonSpec(self._folder_button_label(summary), f"nav:folder:{index}"),))
            rows.append((ButtonSpec("Home", "nav:home"),))
            if has_history:
                rows.append((ButtonSpec("Back", "nav:back"),))
        else:
            rows.extend(self._home_buttons())
            if has_history:
                rows.append((ButtonSpec("Back", "nav:back"),))
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
    ) -> str:
        lines = [f"{intro}: {len(results)} image(s)"]
        if len(folder_summaries) == 1:
            lines.append(f"Folder: {folder_summaries[0].folder_path}")
            if years:
                lines.append(f"Year: {years[0]}")
            if reasons:
                label = "Reason" if len(reasons) == 1 else "Reasons"
                lines.append(f"{label}: {'; '.join(reasons)}")
            return "\n".join(lines)
        lines.append(f"Folders in this batch: {len(folder_summaries)}")
        lines.extend(f"- {summary.folder_path}: {summary.shown_count}" for summary in folder_summaries)
        if len(years) == 1:
            lines.append(f"Year: {years[0]}")
        elif years:
            lines.append("Years: " + ", ".join(str(year) for year in years))
        if reasons:
            lines.append("Matches: " + "; ".join(reasons))
        lines.append("Use Folders to continue in one folder.")
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

    @staticmethod
    def _format_person_detail(detail, heading: str) -> str:
        lines = [f"{heading}: {detail.display_name}"]
        if detail.aliases:
            lines.append("Aliases: " + ", ".join(detail.aliases))
        else:
            lines.append("Aliases: none")
        if detail.folder_paths:
            lines.append("Linked folders:")
            lines.extend(f"- {folder_path}" for folder_path in detail.folder_paths)
        else:
            lines.append("Linked folders: none")
        return "\n".join(lines)

    @staticmethod
    def _home_buttons() -> tuple[tuple[ButtonSpec, ...], ...]:
        return (
            (ButtonSpec("Browse Years", "nav:years"), ButtonSpec("Random Memory", "nav:random")),
            (ButtonSpec("People", "nav:people"), ButtonSpec("Home", "nav:home")),
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
        application.add_handler(CallbackQueryHandler(self._handle_callback, pattern=r"^nav:"))
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
