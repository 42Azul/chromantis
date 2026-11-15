from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Connection

from chromantis.app.interpreter import InterpretedRequest, RuleQueryInterpreter
from chromantis.db.repository import (
    AuthorizedChat,
    ChatPreferences,
    IndexStats,
    InviteCode,
    PersonDetail,
    PersonSummary,
    Repository,
    YearSummary,
)
from chromantis.search.service import SearchResult, SearchService


@dataclass(frozen=True)
class AuthorizedPrincipal:
    chat_id: int
    role: str
    username: str | None
    first_name: str | None
    auth_mode: str


class AuthOperationError(ValueError):
    def __init__(self, code: str, message: str, status: int = 403):
        super().__init__(message)
        self.code = code
        self.status = status


class ApplicationService:
    def __init__(
        self,
        repository: Repository,
        access_code: str | None = None,
        static_viewer_chat_ids: tuple[int, ...] = (),
        static_owner_chat_ids: tuple[int, ...] = (),
    ):
        self.repository = repository
        self.search = SearchService(repository)
        self.interpreter = RuleQueryInterpreter()
        self.access_code = access_code
        self.static_viewer_chat_ids = frozenset(static_viewer_chat_ids)
        self.static_owner_chat_ids = frozenset(static_owner_chat_ids)

    def list_years(self, year_from: int | None = None, year_to: int | None = None) -> list[YearSummary]:
        return self.search.list_year_summaries(year_from=year_from, year_to=year_to)

    def search_folders(self, raw_query: str, limit: int = 10) -> list[SearchResult]:
        return self.search.search_folders(raw_query, limit=limit)

    def search_images(
        self,
        raw_query: str,
        limit: int = 10,
        exclude_paths: tuple[str, ...] = (),
    ) -> list[SearchResult]:
        return self.search.search_images_excluding(raw_query, limit=limit, exclude_paths=exclude_paths)

    def random_images(
        self,
        raw_query: str,
        count: int = 1,
        exclude_paths: tuple[str, ...] = (),
    ) -> list[SearchResult]:
        return self.search.random_images(raw_query, count=count, exclude_paths=exclude_paths)

    def images_in_folder(
        self, folder_path: str, limit: int = 10, exclude_paths: tuple[str, ...] = ()
    ) -> list[SearchResult]:
        return self.search.images_in_folder(folder_path, limit=limit, exclude_paths=exclude_paths)

    def images_in_year(
        self, year: int, limit: int = 10, exclude_paths: tuple[str, ...] = ()
    ) -> list[SearchResult]:
        return self.search.images_in_year(year, limit=limit, exclude_paths=exclude_paths)

    def related_images(
        self,
        folder_path: str,
        year: int,
        limit: int = 10,
        exclude_paths: tuple[str, ...] = (),
        randomize: bool = False,
    ) -> list[SearchResult]:
        return self.search.related_images(
            folder_path,
            year,
            limit=limit,
            exclude_paths=exclude_paths,
            randomize=randomize,
        )

    def images_for_scope(
        self,
        scope: str,
        query: str,
        count: int,
        folder_path: str | None = None,
        year: int | None = None,
        exclude_paths: tuple[str, ...] = (),
    ) -> list[SearchResult]:
        if scope == "search_images":
            return self.search_images(query, limit=count, exclude_paths=exclude_paths)
        if scope == "random_images":
            return self.random_images(query, count=count, exclude_paths=exclude_paths)
        if scope == "same_folder" and folder_path:
            return self.images_in_folder(folder_path, count, exclude_paths)
        if scope == "same_year" and year is not None:
            return self.images_in_year(year, count, exclude_paths)
        if scope == "related_images" and folder_path and year is not None:
            return self.related_images(folder_path, year, count, exclude_paths, randomize=True)
        return []

    def list_people(self) -> list[PersonSummary]:
        return self.search.list_people()

    def get_person_detail(self, identifier: str | int) -> PersonDetail | None:
        return self.search.get_person_detail(identifier)

    def create_person(self, display_name: str, actor_chat_id: int | None = None) -> PersonDetail:
        detail = self.search.create_person(display_name)
        self.repository.record_audit_event(
            action="create_person",
            target_type="person",
            target_id=str(detail.id),
            actor_chat_id=actor_chat_id,
            details={"display_name": display_name},
        )
        return detail

    def rename_person(
        self,
        identifier: str | int,
        new_display_name: str,
        actor_chat_id: int | None = None,
    ) -> PersonDetail:
        detail = self.search.rename_person(identifier, new_display_name)
        self.repository.record_audit_event(
            action="rename_person",
            target_type="person",
            target_id=str(detail.id),
            actor_chat_id=actor_chat_id,
            details={"identifier": identifier, "new_display_name": new_display_name},
        )
        return detail

    def add_person_alias(
        self, identifier: str | int, alias: str, actor_chat_id: int | None = None
    ) -> PersonDetail:
        detail = self.search.add_person_alias(identifier, alias)
        self.repository.record_audit_event(
            action="add_person_alias",
            target_type="person",
            target_id=str(detail.id),
            actor_chat_id=actor_chat_id,
            details={"identifier": identifier, "alias": alias},
        )
        return detail

    def link_person_to_folder(
        self, identifier: str | int, folder_path: str, actor_chat_id: int | None = None
    ) -> PersonDetail:
        detail = self.search.link_person_to_folder(identifier, folder_path)
        self.repository.record_audit_event(
            action="link_person_to_folder",
            target_type="person",
            target_id=str(detail.id),
            actor_chat_id=actor_chat_id,
            details={"identifier": identifier, "folder_path": folder_path},
        )
        return detail

    def unlink_person_from_folder(
        self, identifier: str | int, folder_path: str, actor_chat_id: int | None = None
    ) -> PersonDetail:
        detail = self.search.unlink_person_from_folder(identifier, folder_path)
        self.repository.record_audit_event(
            action="unlink_person_from_folder",
            target_type="person",
            target_id=str(detail.id),
            actor_chat_id=actor_chat_id,
            details={"identifier": identifier, "folder_path": folder_path},
        )
        return detail

    def get_index_stats(self) -> IndexStats:
        return self.repository.get_index_stats()

    def interpret_text(self, text: str) -> InterpretedRequest:
        return self.interpreter.interpret(text)

    def authorize_with_code(
        self,
        chat_id: int,
        code: str,
        username: str | None = None,
        first_name: str | None = None,
    ) -> AuthorizedChat:
        stripped = code.strip()
        if not stripped:
            raise ValueError("Usage: /login <access-code>")
        try:
            return self.repository.redeem_invite(
                stripped,
                chat_id=chat_id,
                username=username,
                first_name=first_name,
            )
        except ValueError:
            if not self.access_code or stripped != self.access_code:
                raise ValueError("Invalid access code.")
        self.repository.authorize_chat(
            chat_id,
            username=username,
            first_name=first_name,
            role="viewer",
        )
        authorized_chat = self.repository.get_authorized_chat(chat_id)
        if authorized_chat is None:
            raise ValueError("Chat authorization could not be stored.")
        return authorized_chat

    def list_authorized_chats(self) -> list[AuthorizedChat]:
        return self.repository.list_authorized_chats()

    def get_dynamic_role(self, chat_id: int) -> str | None:
        return self.repository.get_chat_role(chat_id)

    def get_dynamic_chat(self, chat_id: int) -> AuthorizedChat | None:
        return self.repository.get_authorized_chat(chat_id)

    def get_chat_preferences(self, chat_id: int) -> ChatPreferences | None:
        return self.repository.get_chat_preferences(chat_id)

    def get_chat_language(self, chat_id: int) -> str | None:
        return self.repository.get_chat_language(chat_id)

    def set_chat_language(
        self,
        chat_id: int,
        language: str,
        actor_chat_id: int | None = None,
    ) -> ChatPreferences:
        return self.repository.set_chat_language(
            chat_id=chat_id,
            language=language,
            actor_chat_id=actor_chat_id,
        )

    def is_authorized_chat(self, chat_id: int | None) -> bool:
        return self.resolve_principal(chat_id).role != "none"

    def resolve_principal(
        self,
        chat_id: int | None,
        username: str | None = None,
        first_name: str | None = None,
        *,
        connection: Connection | None = None,
    ) -> AuthorizedPrincipal:
        if chat_id is None:
            return AuthorizedPrincipal(
                chat_id=0,
                role="none",
                username=username,
                first_name=first_name,
                auth_mode="none",
            )
        dynamic = self.repository.get_authorized_chat(chat_id, connection=connection)
        if chat_id in self.static_owner_chat_ids:
            return AuthorizedPrincipal(
                chat_id=chat_id,
                role="owner",
                username=dynamic.username if dynamic else username,
                first_name=dynamic.first_name if dynamic else first_name,
                auth_mode="static_owner",
            )
        if chat_id in self.static_viewer_chat_ids:
            return AuthorizedPrincipal(
                chat_id=chat_id,
                role="viewer",
                username=dynamic.username if dynamic else username,
                first_name=dynamic.first_name if dynamic else first_name,
                auth_mode="static_viewer",
            )
        if dynamic is not None:
            return AuthorizedPrincipal(
                chat_id=chat_id,
                role=dynamic.role,
                username=dynamic.username if dynamic.username is not None else username,
                first_name=dynamic.first_name if dynamic.first_name is not None else first_name,
                auth_mode="dynamic",
            )
        return AuthorizedPrincipal(
            chat_id=chat_id,
            role="none",
            username=username,
            first_name=first_name,
            auth_mode="none",
        )

    def list_effective_authorized_chats(self) -> list[AuthorizedPrincipal]:
        principals: dict[int, AuthorizedPrincipal] = {}
        dynamic_chats = {
            chat.chat_id: chat
            for chat in self.repository.list_authorized_chats()
        }
        static_ids = self.static_viewer_chat_ids | self.static_owner_chat_ids
        for chat_id in sorted(static_ids):
            dynamic = dynamic_chats.get(chat_id)
            principals[chat_id] = self.resolve_principal(
                chat_id,
                username=dynamic.username if dynamic else None,
                first_name=dynamic.first_name if dynamic else None,
            )
        for chat in dynamic_chats.values():
            if chat.chat_id in principals:
                continue
            principals[chat.chat_id] = AuthorizedPrincipal(
                chat_id=chat.chat_id,
                role=chat.role,
                username=chat.username,
                first_name=chat.first_name,
                auth_mode="dynamic",
            )
        return sorted(principals.values(), key=lambda item: (item.chat_id, item.auth_mode))

    def require_admin(
        self, chat_id: int | None, error_code: str, *, connection: Connection | None = None
    ) -> AuthorizedPrincipal:
        principal = self.resolve_principal(chat_id, connection=connection)
        if principal.role not in {"owner", "admin"}:
            raise AuthOperationError(error_code, "Admin privileges are required.")
        return principal

    def set_chat_role(
        self, chat_id: int, role: str, actor_chat_id: int | None
    ) -> AuthorizedPrincipal:
        with self.repository.auth_write() as connection:
            actor = self.resolve_principal(actor_chat_id, connection=connection)
            if actor.role != "owner":
                raise AuthOperationError("authorized_role_owner_only", "Owner privileges are required.")
            target = self.resolve_principal(chat_id, connection=connection)
            if target.auth_mode.startswith("static_"):
                raise AuthOperationError(
                    "static_chat_role", "Static chats cannot be role-changed.", 409
                )
            if target.role == "none":
                raise AuthOperationError("chat_not_authorized", "Chat is not authorized.", 404)
            chat = self.repository.set_chat_role(
                chat_id, role=role, actor_chat_id=actor_chat_id, connection=connection
            )
        return AuthorizedPrincipal(
            chat_id=chat.chat_id,
            role=chat.role,
            username=chat.username,
            first_name=chat.first_name,
            auth_mode="dynamic",
        )

    def revoke_chat_access(self, chat_id: int, actor_chat_id: int | None) -> None:
        with self.repository.auth_write() as connection:
            actor = self.require_admin(
                actor_chat_id, "authorized_revoke_admin_only", connection=connection
            )
            target = self.resolve_principal(chat_id, connection=connection)
            if target.role == "none":
                raise AuthOperationError("chat_not_authorized", "Chat is not authorized.", 404)
            if target.auth_mode.startswith("static_"):
                raise AuthOperationError(
                    "static_chats_cannot_be_revoked", "Static chats cannot be revoked.", 409
                )
            if target.role in {"admin", "owner"} and actor.role != "owner":
                raise AuthOperationError(
                    "authorized_revoke_owner_only", "Owner privileges are required to revoke this chat."
                )
            self.repository.revoke_chat_access(
                chat_id=chat_id, actor_chat_id=actor_chat_id, connection=connection
            )

    def revoke_own_access(self, chat_id: int) -> None:
        with self.repository.auth_write() as connection:
            principal = self.resolve_principal(chat_id, connection=connection)
            if principal.auth_mode.startswith("static_"):
                raise ValueError("Static chats cannot be revoked.")
            self.repository.revoke_chat_access(
                chat_id=chat_id,
                actor_chat_id=chat_id,
                reason="self_logout",
                connection=connection,
            )

    def create_invite(
        self, role: str, created_by_chat_id: int | None, ttl_days: int = 7
    ) -> InviteCode:
        with self.repository.auth_write() as connection:
            actor = self.require_admin(created_by_chat_id, "invite_requires_admin", connection=connection)
            if role == "admin" and actor.role != "owner":
                raise AuthOperationError("invite_admin_owner_only", "Owner privileges are required.")
            if not 1 <= ttl_days <= 30:
                raise ValueError("Invite TTL must be between 1 and 30 days.")
            return self.repository.create_invite(
                role=role, created_by_chat_id=created_by_chat_id, ttl_days=ttl_days, connection=connection
            )

    def list_invites(self, actor_chat_id: int | None) -> list[InviteCode]:
        actor = self.require_admin(actor_chat_id, "invite_list_requires_admin")
        return [
            invite for invite in self.repository.list_invites()
            if invite.role == "viewer" or actor.role == "owner"
        ]

    def revoke_invite(self, code: str, actor_chat_id: int | None) -> InviteCode:
        with self.repository.auth_write() as connection:
            actor = self.require_admin(
                actor_chat_id, "revoke_viewer_invite_admin_only", connection=connection
            )
            invite = next(
                (
                    item for item in self.repository.list_invites(connection=connection)
                    if item.code == code.strip() and (item.role == "viewer" or actor.role == "owner")
                ),
                None,
            )
            if invite is None:
                raise AuthOperationError("unknown_invite_code", "Unknown active invite code.", 404)
            return self.repository.revoke_invite(code, actor_chat_id=actor_chat_id, connection=connection)
