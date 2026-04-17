from __future__ import annotations

from chromantis.search.service import SearchResult


def format_search_results(kind: str, results: list[SearchResult]) -> str:
    if not results:
        return f"No {kind} found."
    lines = []
    for result in results:
        lines.append(f"- {result.path} ({result.reason})")
    return "\n".join(lines)


def format_years(years: list[int]) -> str:
    if not years:
        return "No indexed years yet."
    return "Indexed years: " + ", ".join(str(year) for year in years)
