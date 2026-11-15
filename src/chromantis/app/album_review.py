from __future__ import annotations

import json
import re
from datetime import date
from sqlite3 import Connection

from chromantis.parsing.path_parser import normalize_text


TAG_RULES = {
    "boda": ("boda", "wedding"),
    "cumpleaños": ("cumple", "cumpleanos", "birthday"),
    "excursión": ("excursion", "senderismo", "hiking"),
    "navidad": ("navidad", "nochebuena", "christmas"),
    "playa": ("playa", "beach"),
    "viaje": ("viaje", "trip"),
}


def name_suggestions(folder_name: str) -> dict[str, tuple[str, str]]:
    words = set(re.findall(r"[^\W_]+", normalize_text(folder_name)))
    return {
        normalize_text(label): (label, match)
        for label, aliases in TAG_RULES.items()
        if (match := next((alias for alias in aliases if alias in words), None))
    }


def parse_tag(value: object) -> str:
    if isinstance(value, str) and len(value) <= 40:
        tag = normalize_text(value)
        if tag.isalpha():
            return tag
    raise ValueError("Escribe una etiqueta de una sola palabra, con un máximo de 40 letras.")


def review_folder(
    connection: Connection, *, after: int = 0, reviewed: bool = False, path: str | None = None
):
    sql = """
        SELECT f.id, f.folder_path AS path, f.title, f.event_date, f.year, f.folder_name_raw,
               f.indexed_title, f.indexed_date, f.indexed_year,
               f.title_override, f.date_override, f.note, f.aliases_json, f.context_revision, f.place,
               COALESCE(r.revision, 0) AS revision
        FROM album_metadata f LEFT JOIN album_reviews r ON r.folder_id = f.id
    """
    if path is not None:
        return connection.execute(sql + "WHERE f.folder_path = ?", (path,)).fetchone()
    state = "IS" if reviewed else "IS NOT"
    return connection.execute(
        sql + f"WHERE f.id > ? AND r.reviewed_name {state} f.folder_name_raw ORDER BY f.id LIMIT 1",
        (after,),
    ).fetchone()


def review_item(connection: Connection, folder) -> dict:
    people = connection.execute(
        "SELECT person_id FROM folder_people WHERE folder_id = ? ORDER BY person_id", (folder["id"],)
    )
    decisions = connection.execute(
        """SELECT origin, label, tag, evidence FROM album_tag_decisions
           WHERE folder_id = ? ORDER BY origin, label""",
        (folder["id"],),
    ).fetchall()
    suggestions = {
        key: {"label": label, "tag": key, "evidence": evidence, "state": "pending"}
        for key, (label, evidence) in name_suggestions(folder["folder_name_raw"]).items()
    }
    for decision in decisions:
        if decision["origin"] != "name":
            continue
        label, tag = decision["label"], decision["tag"]
        state = "rejected" if tag is None else "accepted" if tag == label else "corrected"
        suggestions[label] = {
            "label": suggestions.get(label, {}).get("label", label),
            "tag": tag, "evidence": decision["evidence"], "state": state,
        }
    item = dict(folder)
    item["aliases"] = json.loads(item.pop("aliases_json") or "[]")
    return {
        **item,
        "person_ids": [row["person_id"] for row in people],
        "suggestions": suggestions,
        "manual_tags": [row["tag"] for row in decisions if row["origin"] == "manual"],
    }


def save_context(connection: Connection, folder, changes: dict[str, object]) -> bool:
    current = {
        "title": folder["title_override"],
        "event_date": folder["date_override"],
        "note": folder["note"],
        "place": folder["place"],
        "aliases": json.loads(folder["aliases_json"] or "[]"),
    }
    if not changes or changes.keys() - current.keys():
        raise ValueError("Indica qué detalles del álbum quieres cambiar.")
    updated = {**current, **changes}
    for key, limit in (("title", 160), ("note", 500), ("event_date", 10), ("place", 120)):
        value = updated[key]
        if value is not None and (not isinstance(value, str) or len(value.strip()) > limit):
            raise ValueError(f"El campo {key} admite hasta {limit} caracteres.")
        updated[key] = (value.strip() or None) if value else None
    place = updated["place"]
    if place is not None and (not place.isprintable() or not any(ch.isalnum() for ch in place)):
        raise ValueError("Escribe el lugar en una sola línea.")
    event_date = updated["event_date"]
    if event_date is not None:
        try:
            if date.fromisoformat(event_date).isoformat() != event_date:
                raise ValueError
        except ValueError:
            raise ValueError("Indica una fecha válida con formato AAAA-MM-DD.") from None
    aliases = updated["aliases"]
    if (not isinstance(aliases, list) or len(aliases) > 8
            or any(not isinstance(alias, str) or not 1 <= len(alias.strip()) <= 80 or not alias.isprintable()
                   for alias in aliases)):
        raise ValueError("Indica hasta 8 alias de entre 1 y 80 caracteres, uno por línea.")
    by_name = {}
    for alias in aliases:
        by_name.setdefault(normalize_text(alias), alias.strip())
    if "" in by_name:
        raise ValueError("Los alias necesitan un nombre.")
    updated["aliases"] = list(by_name.values())
    if updated == current:
        return False
    connection.execute(
        """INSERT INTO album_context (folder_id, title, event_date, note, aliases_json, revision, place)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (folder_id) DO UPDATE SET title = excluded.title, event_date = excluded.event_date,
               note = excluded.note, aliases_json = excluded.aliases_json, revision = excluded.revision,
               place = excluded.place""",
        (folder["id"], updated["title"], updated["event_date"], updated["note"], json.dumps(updated["aliases"]),
         folder["context_revision"] + 1, place),
    )
    return True


def apply_tag_decisions(
    connection: Connection, folder_id: int, item: dict,
    decisions: dict, manual_add: set[str], manual_remove: set[str],
) -> bool:
    if not decisions.keys() <= item["suggestions"].keys():
        raise ValueError("Alguna sugerencia ya no está disponible.")
    manual_tags = (set(item["manual_tags"]) - manual_remove) | manual_add
    if len(manual_tags) > 20:
        raise ValueError("Se pueden guardar hasta 20 etiquetas manuales por álbum.")
    connection.executemany(
        """INSERT INTO album_tag_decisions (folder_id, origin, label, tag, evidence)
           VALUES (?, 'name', ?, ?, ?)
           ON CONFLICT (folder_id, origin, label) DO UPDATE SET tag = excluded.tag""",
        ((folder_id, label, tag, item["suggestions"][label]["evidence"])
         for label, tag in decisions.items()),
    )
    connection.executemany(
        "DELETE FROM album_tag_decisions WHERE folder_id = ? AND origin = 'manual' AND label = ?",
        ((folder_id, tag) for tag in manual_remove),
    )
    connection.executemany(
        """INSERT OR IGNORE INTO album_tag_decisions (folder_id, origin, label, tag)
           VALUES (?, 'manual', ?, ?)""",
        ((folder_id, tag, tag) for tag in manual_add),
    )
    return all(
        label in decisions or suggestion["state"] != "pending"
        for label, suggestion in item["suggestions"].items()
    )
