from __future__ import annotations

from chromantis.bot.i18n import t
from chromantis.db.repository import YearSummary
from chromantis.search.service import SearchResult


def format_search_results(kind: str, results: list[SearchResult], language: str = "en") -> str:
    if not results:
        return t(language, "search_results_empty", kind=kind)
    lines = []
    for result in results:
        lines.append(f"- {result.path} ({result.reason})")
    return "\n".join(lines)


def format_years(years: list[YearSummary], language: str = "en") -> str:
    if not years:
        return t(language, "years_empty")
    lines = [t(language, "years_header")]
    folder_label = t(language, "year_summary_folder_label")
    image_label = t(language, "year_summary_image_label")
    for summary in years:
        lines.append(
            f"- {summary.year}: {summary.folders} {folder_label}, {summary.images} {image_label}"
        )
    return "\n".join(lines)
