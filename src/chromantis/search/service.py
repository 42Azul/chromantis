from __future__ import annotations

import logging
import random
import sqlite3
from dataclasses import dataclass

from chromantis.db.repository import Repository
from chromantis.search.query_parser import ParsedQuery, parse_query

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    kind: str
    path: str
    title: str
    reason: str
    year: int
    folder_path: str | None = None
    event_date: str | None = None
    ftp_root_path: str | None = None

    @property
    def absolute_path(self) -> str:
        if not self.ftp_root_path:
            return self.path
        return f"{self.ftp_root_path.rstrip('/')}/{self.path.lstrip('/')}"


class SearchService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def list_years(self) -> list[int]:
        years = self.repository.list_years()
        logger.debug("Listing indexed years: %s", years)
        return years

    def search_folders(self, raw_query: str, limit: int = 10) -> list[SearchResult]:
        query = parse_query(raw_query)
        logger.debug("Searching folders raw_query=%r parsed_query=%s limit=%d", raw_query, query, limit)
        with self.repository.connect() as connection:
            rows = connection.execute(
                """
                SELECT f.folder_path, f.title, f.year, f.event_date, f.ftp_root_path,
                       GROUP_CONCAT(DISTINCT t.tag) AS tags
                FROM folders f
                LEFT JOIN folder_tags ft ON ft.folder_id = f.id
                LEFT JOIN tags t ON t.id = ft.tag_id
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
        query = parse_query(raw_query)
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
                {self._image_search_sql()}
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
        with self.repository.connect() as connection:
            sql = self._image_search_sql()
            params: list[object] = [folder_path]
            filters = ["f.folder_path = ?"]
            if exclude_paths:
                placeholders = ", ".join("?" for _ in exclude_paths)
                filters.append(f"i.file_path NOT IN ({placeholders})")
                params.extend(exclude_paths)
            rows = connection.execute(
                f"""
                {sql}
                HAVING {" AND ".join(filters)}
                ORDER BY i.file_path ASC
                """,
                params,
            ).fetchall()
        results = [self._row_to_image_result(row, "same-folder") for row in rows[:limit]]
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
            source_tags = {
                row["tag"]
                for row in connection.execute(
                    """
                    SELECT t.tag
                    FROM folders f
                    JOIN folder_tags ft ON ft.folder_id = f.id
                    JOIN tags t ON t.id = ft.tag_id
                    WHERE f.folder_path = ?
                    """,
                    (folder_path,),
                ).fetchall()
            }
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
        title_text = row["title"]
        reasons = self._match_reasons(query, row["year"], title_text, tokens)
        if not reasons:
            return None
        return SearchResult(
            kind="folder",
            path=row["folder_path"],
            title=title_text,
            reason=", ".join(reasons),
            year=row["year"],
            folder_path=row["folder_path"],
            event_date=row["event_date"],
            ftp_root_path=row["ftp_root_path"],
        )

    def _image_result(self, row: sqlite3.Row, query: ParsedQuery) -> SearchResult | None:
        tokens = set((row["folder_tags"] or "").split(",")) if row["folder_tags"] else set()
        title_text = f'{row["title"]} / {row["filename"]}'
        reasons = self._match_reasons(query, row["year"], title_text, tokens)
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
            ftp_root_path=row["ftp_root_path"],
        )

    @staticmethod
    def _image_search_sql() -> str:
        return """
            SELECT i.file_path, i.filename, f.folder_path, f.title, f.year, f.event_date, f.ftp_root_path,
                   GROUP_CONCAT(DISTINCT t.tag) AS folder_tags
            FROM images i
            JOIN folders f ON f.id = i.folder_id
            LEFT JOIN folder_tags ft ON ft.folder_id = f.id
            LEFT JOIN tags t ON t.id = ft.tag_id
            GROUP BY i.id
        """

    @staticmethod
    def _match_reasons(
        query: ParsedQuery, year: int, searchable_text: str, tags: set[str]
    ) -> list[str]:
        normalized_text = searchable_text.lower()
        reasons: list[str] = []
        if query.year is not None and query.year != year:
            return []
        if query.year is not None:
            reasons.append(f"year={year}")
        for keyword in query.keywords:
            if keyword in normalized_text:
                reasons.append(f'title~"{keyword}"')
            elif keyword in tags:
                reasons.append(f'tag="{keyword}"')
            else:
                return []
        if not query.keywords and query.year is None:
            reasons.append("all")
        return reasons
