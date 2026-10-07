"""Diff DTCC records against state and derive version gaps and date conflicts (DTCC watcher spec §3)."""
from datetime import date

from .dtcc_parse import norm, version_of

CONFLICT_DAYS = 31  # ponytail: "same milestone" heuristic; replace with release-name matching if it misfires


def doc_key(doc: dict) -> str:
    return f"{norm(doc.get('section') or '')}|{norm(doc['title'])}"


def diff_page(old: dict, docs: list) -> tuple:
    new = {doc_key(d): d for d in docs}
    changes, added = [], []
    for k, d in new.items():
        if k not in old:
            added.append(d)
        elif old[k]["date"] != d["date"]:
            changes.append({"kind": "date_moved", "section": d["section"], "title": d["title"],
                            "old_date": old[k]["date"], "date": d["date"]})
    removed = [v for k, v in old.items() if k not in new]
    for d in added:
        twin = next((r for r in removed if r.get("section") == d["section"]), None)
        if twin:
            removed.remove(twin)
            changes.append({"kind": "renamed", "section": d["section"], "title": d["title"],
                            "old_title": twin["title"], "date": d["date"]})
        else:
            changes.append({"kind": "new_doc", "section": d["section"], "title": d["title"], "date": d["date"]})
    return changes, removed


def published(docs: list) -> tuple | None:
    versions = [v for v in (version_of(d["title"]) for d in docs) if v]
    return max(versions) if versions else None


def vstr(v: tuple) -> str:
    return f"v{v[0]:02d}-{v[1]}"


def conflicts(release_dates: list, notice_dates: dict, today: str) -> list:
    """Release-page milestone vs the same label in a notice, 1-31 days apart, not both in the past."""
    out = []
    for label, a in release_dates:
        for number, dates in notice_dates.items():
            for other, b in dates:
                if other != label or max(a, b) < today:
                    continue
                if 1 <= abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= CONFLICT_DAYS:
                    out.append((label, a, b, number))
    return out
