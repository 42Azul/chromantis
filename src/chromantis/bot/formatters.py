from __future__ import annotations

from chromantis.db.repository import YearSummary
from chromantis.search.service import SearchResult


def format_search_results(kind: str, results: list[SearchResult]) -> str:
    if not results:
        return f"No {kind} found."
    lines = []
    for result in results:
        lines.append(f"- {result.path} ({result.reason})")
    return "\n".join(lines)


def format_years(years: list[YearSummary]) -> str:
    if not years:
        return "No indexed years yet."
    lines = ["Indexed years:"]
    for summary in years:
        lines.append(
            f"- {summary.year}: {summary.folders} folder(s), {summary.images} image(s)"
        )
    return "\n".join(lines)
