from __future__ import annotations

import json
import logging
import random
import sqlite3
from dataclasses import dataclass
from functools import lru_cache

from chromantis.db.repository import PersonDetail, PersonSummary, Repository, YearSummary
from chromantis.parsing.path_parser import normalize_text
from chromantis.search.query_parser import ParsedQuery, parse_query

logger = logging.getLogger(__name__)

_FOLDER_TAGS_SQL = """(
    SELECT GROUP_CONCAT(tag) FROM (
        SELECT t.tag FROM folder_tags ft JOIN tags t ON t.id = ft.tag_id WHERE ft.folder_id = f.id
        UNION
        SELECT d.tag FROM album_tag_decisions d WHERE d.folder_id = f.id AND d.tag IS NOT NULL
    )
)"""


@dataclass(frozen=True)
class SearchResult:
    kind: str
    path: str
    title: str
    reason: str
    year: int
    folder_path: str | None = None
    event_date: str | None = None


class SearchService:
    def __init__(self, repository: Repository, include_enrichment: bool = False):
        self.repository = repository
        self.include_enrichment = include_enrichment

    def list_years(self) -> list[int]:
        years = self.repository.list_years()
        logger.debug("Listing indexed years: %s", years)
        return years

    def list_year_summaries(
        self, year_from: int | None = None, year_to: int | None = None
    ) -> list[YearSummary]:
        summaries = self.repository.list_year_summaries(year_from=year_from, year_to=year_to)
        logger.debug(
            "Listing indexed year summaries year_from=%s year_to=%s summaries=%s",
            year_from,
            year_to,
            summaries,
        )
        return summaries

    def list_people(self) -> list[PersonSummary]:
        people = self.repository.list_people()
        logger.debug("Listing curated people: %s", people)
        return people

    def get_person_detail(self, identifier: str | int) -> PersonDetail | None:
        detail = self.repository.get_person_detail(identifier)
        logger.debug("Fetched person detail identifier=%r detail=%s", identifier, detail)
        return detail

    def create_person(self, display_name: str) -> PersonDetail:
        detail = self.repository.create_person(display_name)
        logger.info("Created person display_name=%r id=%d", display_name, detail.id)
        return detail

    def rename_person(self, identifier: str | int, new_display_name: str) -> PersonDetail:
        detail = self.repository.rename_person(identifier, new_display_name)
        logger.info(
            "Renamed person identifier=%r new_display_name=%r id=%d",
            identifier,
            new_display_name,
            detail.id,
        )
        return detail

    def add_person_alias(self, identifier: str | int, alias: str) -> PersonDetail:
        detail = self.repository.add_person_alias(identifier, alias)
        logger.info("Added person alias identifier=%r alias=%r id=%d", identifier, alias, detail.id)
        return detail

    def link_person_to_folder(self, identifier: str | int, folder_path: str) -> PersonDetail:
        detail = self.repository.link_person_to_folder(identifier, folder_path)
        logger.info("Linked person identifier=%r folder=%r id=%d", identifier, folder_path, detail.id)
        return detail

    def unlink_person_from_folder(self, identifier: str | int, folder_path: str) -> PersonDetail:
        detail = self.repository.unlink_person_from_folder(identifier, folder_path)
        logger.info(
            "Unlinked person identifier=%r folder=%r id=%d",
            identifier,
            folder_path,
            detail.id,
        )
        return detail

    def search_folders(self, raw_query: str, limit: int = 10) -> list[SearchResult]:
        query = self._parse_query(raw_query)
        logger.debug("Searching folders raw_query=%r parsed_query=%s limit=%d", raw_query, query, limit)
        with self.repository.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT f.folder_path, f.title, f.year, f.event_date, f.indexed_title, f.indexed_year, f.aliases_json,
                       {_FOLDER_TAGS_SQL} AS tags,
                       GROUP_CONCAT(DISTINCT p.id) AS person_ids,
                       GROUP_CONCAT(DISTINCT p.display_name) AS people_names
                FROM album_metadata f
                LEFT JOIN folder_people fp ON fp.folder_id = f.id
                LEFT JOIN people p ON p.id = fp.person_id
                GROUP BY f.id
                ORDER BY f.year DESC, f.folder_path ASC
                """
            ).fetchall()
        matches = [self._folder_result(row, query) for row in rows]
        results = [result for result in matches if result][:limit]
        logger.info("Folder search query=%r returned %d results", raw_query, len(results))
        return results

    def search_images(self, raw_query: str, limit: int = 10) -> list[SearchResult]:
        return self.search_images_excluding(raw_query, limit=limit, exclude_paths=())

    def search_images_excluding(
        self, raw_query: str, limit: int = 10, exclude_paths: tuple[str, ...] = ()
    ) -> list[SearchResult]:
        query = self._parse_query(raw_query)
        logger.debug(
            "Searching images raw_query=%r parsed_query=%s limit=%d exclude=%d",
            raw_query,
            query,
            limit,
            len(exclude_paths),
        )
        excluded = set(exclude_paths)
        with self.repository.connect() as connection:
            rows = connection.execute(
                f"""
                {self._image_search_sql(self.include_enrichment)}
                ORDER BY f.year DESC, i.file_path ASC
                """
            ).fetchall()
        matches = [self._image_result(row, query) for row in rows]
        results = [
            result
            for result in matches
            if result and result.path not in excluded
        ][:limit]
        logger.info("Image search query=%r returned %d results", raw_query, len(results))
        return results

    def random_image(self, raw_query: str, limit: int = 10) -> SearchResult | None:
        matches = self.search_images(raw_query, limit=limit)
        if not matches:
            logger.info("Random image query=%r returned no matches", raw_query)
            return None
        result = random.choice(matches)
        logger.info("Random image query=%r selected %s", raw_query, result.path)
        return result

    def random_images(
        self,
        raw_query: str,
        count: int = 1,
        pool_limit: int = 100,
        exclude_paths: tuple[str, ...] = (),
    ) -> list[SearchResult]:
        matches = self.search_images_excluding(
            raw_query,
            limit=max(count, pool_limit),
            exclude_paths=exclude_paths,
        )
        if not matches:
            logger.info("Random image query=%r returned no matches", raw_query)
            return []
        sample_size = min(count, len(matches))
        results = random.sample(matches, sample_size)
        logger.info("Random image query=%r selected %d images", raw_query, len(results))
        return results

    def images_in_folder(
        self, folder_path: str, limit: int = 10, exclude_paths: tuple[str, ...] = ()
    ) -> list[SearchResult]:
        excluded = set(exclude_paths)
        with self.repository.connect() as connection:
            rows = connection.execute(
                """
                SELECT i.file_path, i.filename, f.folder_path, f.title, f.year, f.event_date
                FROM album_metadata f JOIN images i ON i.folder_id = f.id
                WHERE f.folder_path = ?
                ORDER BY i.file_path ASC
                LIMIT ?
                """,
                (folder_path, limit + len(excluded) if limit >= 0 else -1),
            ).fetchall()
        results = [
            self._row_to_image_result(row, "same-folder")
            for row in rows
            if row["file_path"] not in excluded
        ][:limit]
        logger.info(
            "Folder image search folder_path=%r exclude=%d returned %d results",
            folder_path,
            len(exclude_paths),
            len(results),
        )
        return results

    def images_in_year(
        self, year: int, limit: int = 10, exclude_paths: tuple[str, ...] = ()
    ) -> list[SearchResult]:
        excluded = set(exclude_paths)
        with self.repository.connect() as connection:
            rows = connection.execute(
                f"""
                {self._image_search_sql()}
                HAVING f.year = ?
                ORDER BY i.file_path ASC
                """,
                (year,),
            ).fetchall()
        results = [
            self._row_to_image_result(row, f"same-year={year}")
            for row in rows
            if row["file_path"] not in excluded
        ][:limit]
        logger.info(
            "Year image search year=%d exclude=%d returned %d results",
            year,
            len(exclude_paths),
            len(results),
        )
        return results

    def related_images(
        self,
        folder_path: str,
        year: int,
        limit: int = 10,
        exclude_paths: tuple[str, ...] = (),
        randomize: bool = False,
    ) -> list[SearchResult]:
        excluded = set(exclude_paths)
        with self.repository.connect() as connection:
            source = connection.execute(
                f"SELECT {_FOLDER_TAGS_SQL} AS tags FROM folders f WHERE f.folder_path = ?",
                (folder_path,),
            ).fetchone()
            source_tags = set(source["tags"].split(",")) if source and source["tags"] else set()
            rows = connection.execute(
                f"""
                {self._image_search_sql()}
                HAVING f.year = ?
                ORDER BY i.file_path ASC
                """,
                (year,),
            ).fetchall()

        scored: list[tuple[int, SearchResult]] = []
        for row in rows:
            if row["file_path"] in excluded or row["folder_path"] == folder_path:
                continue
            row_tags = set((row["folder_tags"] or "").split(",")) if row["folder_tags"] else set()
            overlap = len(source_tags & row_tags)
            if overlap == 0:
                continue
            scored.append(
                (
                    overlap,
                    self._row_to_image_result(row, f"related-tags={overlap}"),
                )
            )

        if randomize and scored:
            sample_size = min(limit, len(scored))
            results = [item[1] for item in random.sample(scored, sample_size)]
        else:
            results = [item[1] for item in sorted(scored, key=lambda item: (-item[0], item[1].path))[:limit]]
        logger.info(
            "Related image search folder=%r year=%d exclude=%d returned %d results",
            folder_path,
            year,
            len(exclude_paths),
            len(results),
        )
        return results

    def _folder_result(self, row: sqlite3.Row, query: ParsedQuery) -> SearchResult | None:
        tokens = set((row["tags"] or "").split(",")) if row["tags"] else set()
        reasons = self._match_reasons(query, row, tokens)
        if not reasons:
            return None
        return SearchResult(
            kind="folder",
            path=row["folder_path"],
            title=row["title"],
            reason=", ".join(reasons),
            year=row["year"],
            folder_path=row["folder_path"],
            event_date=row["event_date"],
        )

    def _image_result(self, row: sqlite3.Row, query: ParsedQuery) -> SearchResult | None:
        tokens = set((row["folder_tags"] or "").split(",")) if row["folder_tags"] else set()
        reasons = self._match_reasons(
            query, row, tokens, filename=row["filename"],
            enrichment_text=row["enrichment_text"] if self.include_enrichment else "",
        )
        if not reasons:
            return None
        return self._row_to_image_result(row, ", ".join(reasons))

    @staticmethod
    def _row_to_image_result(row: sqlite3.Row, reason: str) -> SearchResult:
        return SearchResult(
            kind="image",
            path=row["file_path"],
            title=f'{row["title"]} / {row["filename"]}',
            reason=reason,
            year=row["year"],
            folder_path=row["folder_path"],
            event_date=row["event_date"],
        )

    @staticmethod
    def _image_search_sql(include_enrichment: bool = False) -> str:
        enriched_column = """
            , COALESCE((
                SELECT GROUP_CONCAT(e.searchable_text, ' ')
                FROM image_enrichment e WHERE e.image_id = i.id AND e.source_root = f.ftp_root_path
                  AND e.error IS NULL
                  AND e.source_modified_at IS i.ftp_modified_at AND e.source_size IS i.file_size
            ), '') AS enrichment_text
        """ if include_enrichment else ""
        return f"""
            SELECT i.file_path, i.filename, f.folder_path, f.title, f.year, f.event_date,
                   f.indexed_title, f.indexed_year, f.aliases_json,
                   {_FOLDER_TAGS_SQL} AS folder_tags,
                   GROUP_CONCAT(DISTINCT p.id) AS person_ids,
                   GROUP_CONCAT(DISTINCT p.display_name) AS people_names
                   {enriched_column}
            FROM images i
            JOIN album_metadata f ON f.id = i.folder_id
            LEFT JOIN folder_people fp ON fp.folder_id = f.id
            LEFT JOIN people p ON p.id = fp.person_id
            GROUP BY i.id
        """

    def _parse_query(self, raw_query: str) -> ParsedQuery:
        return parse_query(raw_query, alias_map=self.repository.list_alias_map())

    def _match_reasons(
        self,
        query: ParsedQuery,
        row: sqlite3.Row,
        tags: set[str],
        filename: str = "",
        enrichment_text: str = "",
    ) -> list[str]:
        year = row["year"]
        aliases = _normalized_aliases(row["aliases_json"]) if row["aliases_json"] else ()
        original_title = row["indexed_title"]
        corrected_title = normalize_text(row["title"]) if row["title"] != original_title else ""
        phrase = query.phrase.replace("’", "'")
        literal = query.literal_phrase.replace("’", "'")
        # When the entire input names an album, a year inside that name is literal.
        if phrase and literal != phrase:
            exact_reason = _album_name_reason(literal, aliases, corrected_title, row["title"])
            if exact_reason:
                return [exact_reason]
            if literal == original_title.replace("’", "'"):
                return [f'title~"{original_title}"']
        reasons: list[str] = []
        if query.year_from is not None and year < query.year_from:
            return []
        if query.year_to is not None and year > query.year_to:
            return []
        if query.year_from is not None and query.year_to is not None and query.year_from == query.year_to:
            reasons.append(f"year={year}")
        elif query.year_from is not None and query.year_to is not None:
            reasons.append(f"year_range={query.year_from}-{query.year_to}")
        if reasons and year != row["indexed_year"]:
            reasons.append(f"year_corrected={year}")
        exact_reason = _album_name_reason(phrase, aliases, corrected_title, row["title"])
        if exact_reason:
            return [*reasons, exact_reason]

        normalized_text = f"{original_title} / {filename.lower()}" if filename else original_title
        available_person_ids = _person_ids_from_row(row["person_ids"])
        for person in query.people:
            if person.id in available_person_ids:
                reasons.append(f'person="{person.display_name}"')
                continue
            if _person_term_matches(person.search_terms, normalized_text, tags):
                reasons.append(f'person_text="{person.display_name}"')
                continue
            return []
        for keyword in query.keywords:
            alias = next((alias for alias, name in aliases if keyword.replace("’", "'") in name.split()), None)
            if keyword in normalized_text:
                reasons.append(f'title~"{keyword}"')
            elif keyword in corrected_title:
                reasons.append(f'album_title~"{keyword}"')
            elif alias:
                reasons.append(f'album_alias="{alias}"')
            elif keyword in tags:
                reasons.append(f'tag="{keyword}"')
            elif keyword in enrichment_text:
                reasons.append(f'enrichment~"{keyword}"')
            else:
                return []
        if not query.keywords and query.year_from is None and not query.people:
            reasons.append("all")
        return list(dict.fromkeys(reasons))


@lru_cache(maxsize=128)
def _normalized_aliases(aliases_json: str) -> tuple[tuple[str, str], ...]:
    return tuple((alias, normalize_text(alias).replace("’", "'")) for alias in json.loads(aliases_json))


def _album_name_reason(
    phrase: str, aliases: tuple[tuple[str, str], ...], corrected_title: str, title: str,
) -> str | None:
    alias = next((alias for alias, name in aliases if name == phrase), None)
    if alias is not None:
        return f'album_alias="{alias}"'
    if corrected_title and phrase == corrected_title.replace("’", "'"):
        return f'album_title="{title}"'
    return None


def _person_ids_from_row(value: str | None) -> set[int]:
    if not value:
        return set()
    return {int(item) for item in value.split(",") if item}


def _person_term_matches(
    search_terms: tuple[str, ...], normalized_text: str, tags: set[str]
) -> bool:
    for term in search_terms:
        if term in normalized_text:
            return True
        if " " not in term and term in tags:
            return True
    return False
