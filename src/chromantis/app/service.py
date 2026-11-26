from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import partial
from sqlite3 import Connection

from chromantis.app.album_review import (
    apply_tag_decisions,
    parse_tag,
    review_batch,
    review_folder,
    review_item,
    save_context,
    save_review_progress,
)
from chromantis.app.interpreter import InterpretedRequest, QueryInterpreter, RuleQueryInterpreter
from chromantis.app.recall import MAX_YEAR, MIN_YEAR, Refinement, normalize_album_request, refine
from chromantis.db.album_shares import AlbumShareStore
from chromantis.db.collections import CollectionStore
from chromantis.db.family_access import FamilyAccess, FamilySession
from chromantis.db.photo_tags import find_photos, photo_annotations, update_photo_annotations
from chromantis.db.repository import (
    AuthorizedChat,
    ChatPreferences,
    IndexStats,
    InviteCode,
    PersonDetail,
    PersonSummary,
    Repository,
    SavedSearch,
    YearSummary,
)
from chromantis.search.query_parser import split_recall
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
        interpreter: QueryInterpreter | None = None,
        include_enrichment: bool = False,
        curator_chat_ids: tuple[int, ...] = (),
    ):
        self.repository = repository
        self.search = SearchService(repository, include_enrichment=include_enrichment)
        self.interpreter = interpreter if interpreter is not None else RuleQueryInterpreter()
        self.access_code = access_code
        self.static_viewer_chat_ids = frozenset(static_viewer_chat_ids)
        self.static_owner_chat_ids = frozenset(static_owner_chat_ids)
        self.curator_chat_ids = frozenset(curator_chat_ids)
        self.family_access = FamilyAccess(repository)

    def list_years(self, year_from: int | None = None, year_to: int | None = None) -> list[YearSummary]:
        return self.search.list_year_summaries(year_from=year_from, year_to=year_to)

    def album_tags(self, *, limit: int, offset: int, name: str = "") -> list[dict[str, object]]:
        return self.search.album_tags(limit=limit, offset=offset, name=name)

    def photo_tags(self, *, limit: int, offset: int, name: str = "") -> list[dict[str, object]]:
        return self.search.photo_tags(limit=limit, offset=offset, name=name)

    def search_folders(
        self, raw_query: str, limit: int = 10, *, place: str = "", date_from: str | None = None,
        date_to: str | None = None, chronological: bool = False, offset: int = 0, tag: str | None = None,
    ) -> list[SearchResult]:
        query = normalize_album_request(raw_query, self.repository.list_alias_map)
        return self.search.search_folders(
            query, limit=limit, place=place, date_from=date_from, date_to=date_to,
            chronological=chronological, offset=offset, tag=tag,
        )

    def album_search_filters(self, raw_query: str) -> dict[str, object]:
        if len(raw_query) > 2000:
            raise ValueError("La consulta admite hasta 2000 caracteres.")
        query = normalize_album_request(raw_query, self.repository.list_alias_map)
        text, filters = split_recall(query)
        active = []
        if filters.years:
            first, last = filters.years
            if first == last:
                label = str(first)
            elif first == MIN_YEAR:
                label = f"≤ {last}"
            elif last == MAX_YEAR:
                label = f"≥ {first}"
            else:
                label = f"{first}–{last}"
            active.append({"kind": "year", "label": label, "without": replace(filters, years=None).apply(text)})
        if filters.people:
            names = {person.id: person.display_name for person in self.repository.list_alias_map().values()}
            for person_id in filters.people:
                remaining = tuple(value for value in filters.people if value != person_id)
                active.append({
                    "kind": "person", "label": names.get(person_id, str(person_id)),
                    "without": replace(filters, people=remaining).apply(text),
                })
        if filters.album:
            with self.repository.session() as connection:
                row = connection.execute(
                    "SELECT title FROM album_metadata WHERE folder_path = ?", (filters.album,)
                ).fetchone()
            active.append({
                "kind": "album", "label": row["title"] if row else filters.album,
                "without": replace(filters, album=None).apply(text),
            })
        return {"q": query, "text": text, "active": active}

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

    def search_confirmed_images(
        self, person: str | int, *, limit: int = 10, offset: int = 0, tag: str | None = None,
        year: int | None = None,
    ) -> list[SearchResult]:
        return self.search.search_confirmed_images(
            person, limit=limit, offset=offset, tag=parse_tag(tag) if tag is not None else None, year=year,
        )

    def search_manually_tagged_images(
        self, tag: str, *, limit: int = 10, offset: int = 0, year: int | None = None,
    ) -> list[SearchResult]:
        return self.search.search_manually_tagged_images(parse_tag(tag), limit=limit, offset=offset, year=year)

    def images_in_folder(
        self, folder_path: str, limit: int = 10, exclude_paths: tuple[str, ...] = (), *, offset: int = 0,
    ) -> list[SearchResult]:
        return self.search.images_in_folder(
            folder_path, limit=limit, exclude_paths=exclude_paths, offset=offset,
        )

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

    def can_curate_albums(self, principal: AuthorizedPrincipal) -> bool:
        return principal.role in {"owner", "admin"} or (
            principal.role == "viewer" and principal.chat_id in self.curator_chat_ids
        )

    def require_album_curator(self, actor: int | FamilySession, connection: Connection | None = None) -> None:
        if isinstance(actor, FamilySession):
            if connection is not None:
                active = self.family_access.still_active(connection, actor)
            else:
                with self.repository.session() as check_connection:
                    active = self.family_access.still_active(check_connection, actor)
            if not active:
                raise AuthOperationError("family_session_expired", "La sesión familiar ha caducado.", 401)
        elif not self.can_curate_albums(self.resolve_principal(actor, connection=connection)):
            raise AuthOperationError("album_curation_required", "No tienes permiso para etiquetar álbumes.")

    def get_album_review(
        self, actor: int | FamilySession, *, after: int = 0, reviewed: bool = False, path: str | None = None
    ) -> dict | None:
        with self.repository.session() as connection:
            connection.execute("BEGIN")
            self.require_album_curator(actor, connection)
            folder = review_folder(connection, after=after, reviewed=reviewed, path=path)
            return review_item(connection, folder) if folder is not None else None

    def get_photo_tags(self, actor: int | FamilySession, paths: list[str]) -> list[dict]:
        with self.repository.session() as connection:
            connection.execute("BEGIN")
            self.require_album_curator(actor, connection)
            photos = find_photos(connection, paths)
            if any(path not in photos for path in paths):
                raise AuthOperationError("photo_not_found", "Indexed photo not found.", 404)
            return [photo_annotations(connection, photos[path]) for path in paths]

    def save_photo_tags(
        self, actor: int | FamilySession, photos: dict[str, str], *,
        add_people: set[int], remove_people: set[int], manual_add: set[str], manual_remove: set[str],
    ) -> list[dict]:
        with self.repository.write_transaction() as connection:
            self.require_album_curator(actor, connection)
            manual_add = {parse_tag(tag) for tag in manual_add}
            manual_remove = {parse_tag(tag) for tag in manual_remove}
            if add_people & remove_people or manual_add & manual_remove:
                raise ValueError("The same person or tag cannot be added and removed together.")
            if not photos or not (add_people or remove_people or manual_add or manual_remove):
                raise ValueError("Select photos and at least one change.")
            indexed = find_photos(connection, list(photos))
            if any(path not in indexed or indexed[path]["photo_identity"] != identity
                   for path, identity in photos.items()):
                raise AuthOperationError("photo_changed", "An indexed photo changed. Reload the selection.", 409)
            for person_id in add_people | remove_people:
                if self.repository.resolve_person(connection, person_id) is None:
                    raise ValueError("A selected person is missing from the directory.")
            chat_id = actor if isinstance(actor, int) else None
            family_audit = {"family_access_id": actor.id} if isinstance(actor, FamilySession) else {}
            items = []
            for path in photos:
                photo = indexed[path]
                item = photo_annotations(connection, photo)
                present_people = {person["person_id"] for person in item["people"]}
                present_tags = {tag["tag"] for tag in item["manual_tags"]}
                changes = {
                    "add_people": add_people - present_people,
                    "remove_people": remove_people & present_people,
                    "manual_add": manual_add - present_tags,
                    "manual_remove": manual_remove & present_tags,
                }
                if any(changes.values()):
                    update_photo_annotations(connection, photo["id"], **changes)
                    self.repository.record_audit_event(
                        "save_photo_tags", "image", path,
                        {"origin": "manual", "identity": photo["photo_identity"], **family_audit,
                         **{key: sorted(values) for key, values in changes.items()}},
                        chat_id, connection=connection,
                    )
                    item = photo_annotations(connection, photo)
                items.append(item)
            return items

    def album_people_directory(self, actor: int | FamilySession) -> list[dict]:
        self.require_album_curator(actor)
        people = {}
        with self.repository.session() as connection:
            for row in connection.execute(
                """SELECT p.id, p.display_name, a.alias FROM people p
                   LEFT JOIN person_aliases a ON p.id = a.person_id
                   ORDER BY p.display_name, p.id, a.alias_normalized"""
            ):
                person = people.setdefault(
                    row["id"], {"id": row["id"], "display_name": row["display_name"], "aliases": []}
                )
                if row["alias"] is not None:
                    person["aliases"].append(row["alias"])
        return list(people.values())

    def get_album_review_batch(self, actor: int | FamilySession, limit: int = 50) -> list[dict]:
        with self.repository.session() as connection:
            connection.execute("BEGIN")
            self.require_album_curator(actor, connection)
            return review_batch(connection, limit)

    def edit_album_context(
        self, actor: int | FamilySession, path: str, folder_id: int, revision: int, changes: dict[str, object],
    ) -> dict:
        with self.repository.write_transaction() as connection:
            self.require_album_curator(actor, connection)
            folder = review_folder(connection, path=path)
            if folder is None or (folder["id"], folder["context_revision"]) != (folder_id, revision):
                raise AuthOperationError(
                    "album_context_changed", "Los detalles del álbum han cambiado. Vuelve a abrirlo.", 409
                )
            if save_context(connection, folder, changes):
                audit: dict[str, object] = {"fields": sorted(changes)}
                if isinstance(actor, FamilySession):
                    audit["family_access_id"] = actor.id
                self.repository.record_audit_event(
                    "edit_album_context", "folder", path, audit,
                    actor if isinstance(actor, int) else None, connection=connection,
                )
                folder = review_folder(connection, path=path)
                assert folder is not None
            return review_item(connection, folder)

    def save_album_review(
        self, actor: int | FamilySession, path: str, folder_id: int, revision: int, *,
        add_people: set[int], remove_people: set[int], new_person: str | None,
        decisions: dict[str, str | None], manual_add: set[str], manual_remove: set[str],
    ) -> None:
        with self.repository.write_transaction() as connection:
            self.require_album_curator(actor, connection)
            chat_id = actor if isinstance(actor, int) else None
            family_audit = {"family_access_id": actor.id} if isinstance(actor, FamilySession) else {}
            folder = review_folder(connection, path=path)
            if folder is None or (folder["id"], folder["revision"]) != (folder_id, revision):
                raise AuthOperationError(
                    "album_review_changed", "El álbum ha cambiado. Vuelve a abrirlo antes de guardar.", 409
                )
            item = review_item(connection, folder)
            reviewed = apply_tag_decisions(
                connection, folder_id, item, decisions, manual_add, manual_remove
            )
            for person_id in add_people:
                if connection.execute("SELECT 1 FROM people WHERE id = ?", (person_id,)).fetchone() is None:
                    raise ValueError("Alguna de las personas seleccionadas ya no está disponible.")
            if new_person:
                person = self.repository.create_person(new_person, connection=connection)
                add_people = add_people | {person.id}
                self.repository.record_audit_event(
                    "create_person", "person", str(person.id), {"display_name": person.display_name, **family_audit},
                    chat_id, connection=connection,
                )
            connection.executemany(
                "DELETE FROM folder_people WHERE folder_id = ? AND person_id = ?",
                ((folder_id, person_id) for person_id in remove_people),
            )
            connection.executemany(
                "INSERT OR IGNORE INTO folder_people (folder_id, person_id) VALUES (?, ?)",
                ((folder_id, person_id) for person_id in add_people),
            )
            save_review_progress(connection, folder, reviewed)
            self.repository.record_audit_event(
                "save_album_review", "folder", path,
                {"add_people": sorted(add_people), "remove_people": sorted(remove_people),
                 "decisions": decisions, "manual_add": sorted(manual_add), "manual_remove": sorted(manual_remove),
                 **family_audit},
                chat_id, connection=connection,
            )

    def save_album_review_batch(
        self, actor: int | FamilySession, entries: list[dict[str, object]],
    ) -> None:
        with self.repository.write_transaction() as connection:
            self.require_album_curator(actor, connection)
            chat_id = actor if isinstance(actor, int) else None
            family_audit = {"family_access_id": actor.id} if isinstance(actor, FamilySession) else {}
            seen = set()
            for entry in entries:
                identity = entry["id"]
                if identity in seen:
                    raise ValueError("Cada álbum solo puede aparecer una vez por lote.")
                seen.add(identity)
                folder = review_folder(connection, path=entry["path"])
                if folder is None or (folder["id"], folder["revision"]) != (
                    entry["id"], entry["revision"],
                ):
                    raise AuthOperationError(
                        "album_review_changed", "Algún álbum ha cambiado. Recarga el lote.", 409
                    )
                item = review_item(connection, folder)
                label = entry["label"]
                suggestion = item["suggestions"].get(label)
                if suggestion is None or suggestion["state"] != "pending":
                    raise AuthOperationError(
                        "album_review_changed", "Alguna sugerencia ya ha sido revisada. Recarga el lote.", 409
                    )
                tag = entry.get("tag") if entry["decision"] == "corrected" else None
                if entry["decision"] == "accepted":
                    tag = label
                elif entry["decision"] == "corrected" and (tag is None or tag == label):
                    raise ValueError("Elige una etiqueta distinta para corregir la sugerencia.")
                reviewed = apply_tag_decisions(
                    connection, folder["id"], item, {label: tag}, set(), set()
                )
                save_review_progress(connection, folder, reviewed)
            self.repository.record_audit_event(
                "save_album_review_batch", "folder_batch", str(len(entries)),
                {"items": entries, **family_audit}, chat_id, connection=connection,
            )

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

    def remember_search(self, chat_id: int | None, kind: str, query: str, count: int) -> None:
        if chat_id is None or not query.strip():
            return
        with self.repository.write_transaction() as connection:
            if self.resolve_principal(chat_id, connection=connection).role != "none":
                self.repository.record_search(connection, chat_id, kind, query.strip(), count)

    def set_search_pinned(self, chat_id: int, search_id: int, pinned: bool) -> SavedSearch | None:
        with self.repository.write_transaction() as connection:
            if self.resolve_principal(chat_id, connection=connection).role == "none":
                raise AuthOperationError("unauthorized", "Chat is not authorized.", 401)
            return self.repository.set_search_pinned(connection, chat_id, search_id, pinned)

    @contextmanager
    def owner_collections(self, chat_id: int, *, write: bool = False):
        transaction = self.repository.write_transaction() if write else self.repository.session()
        with transaction as connection:
            if not write:
                connection.execute("BEGIN")
            if self.resolve_principal(chat_id, connection=connection).role != "owner":
                raise AuthOperationError("collections_owner", "Owner privileges are required for collections.")
            yield CollectionStore(connection, chat_id)

    @contextmanager
    def owner_album_shares(self, chat_id: int, *, write: bool = False):
        transaction = self.repository.write_transaction() if write else self.repository.session()
        with transaction as connection:
            if not write:
                connection.execute("BEGIN")
            if self.resolve_principal(chat_id, connection=connection).role != "owner":
                raise AuthOperationError("album_shares_owner", "Owner privileges are required for album shares.")
            yield AlbumShareStore(connection, chat_id)

    @contextmanager
    def album_share(self, secret: object):
        with self.repository.session() as connection:
            connection.execute("BEGIN")
            store = AlbumShareStore(connection)
            share = store.resolve(secret)
            yield store, share

    def get_index_stats(self) -> IndexStats:
        return self.repository.get_index_stats()

    def interpret_text(self, text: str) -> InterpretedRequest:
        return self.interpreter.interpret(text)

    def refine_query(self, base: str, text: str, *, tag: str | None = None) -> Refinement:
        aliases = self.repository.list_alias_map()
        return refine(
            normalize_album_request(base, lambda: aliases), text, aliases,
            partial(self.search_folders, tag=tag), allow_empty=tag is not None,
        )

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
        with self.repository.write_transaction() as connection:
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
        with self.repository.write_transaction() as connection:
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
        with self.repository.write_transaction() as connection:
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
        with self.repository.write_transaction() as connection:
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
        with self.repository.write_transaction() as connection:
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
