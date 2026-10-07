from vaultlib import dtcc_diff as dd


def doc(title, date, section="S"):
    return {"section": section, "title": title, "date": date}


def state(*docs):
    return {dd.doc_key(d): d for d in docs}


def test_new_moved_renamed_and_removed():
    old = state(doc("Guide", "2025-01-01"), doc("Layouts v26-7", "2026-04-08"), doc("Gone", "2024-01-01", "T"))
    new = [doc("Guide", "2025-02-01"), doc("Layouts v26-8", "2026-09-30"), doc("Fresh", "2026-10-01", "U")]
    changes, removed = dd.diff_page(old, new)
    assert {c["kind"] for c in changes} == {"date_moved", "renamed", "new_doc"}
    renamed = next(c for c in changes if c["kind"] == "renamed")
    assert (renamed["old_title"], renamed["title"]) == ("Layouts v26-7", "Layouts v26-8")
    moved = next(c for c in changes if c["kind"] == "date_moved")
    assert (moved["old_date"], moved["date"]) == ("2025-01-01", "2025-02-01")
    assert [r["title"] for r in removed] == ["Gone"]


def test_title_case_and_spacing_do_not_count_as_change():
    old = state(doc("Record  Layouts", "2025-01-01"))
    assert dd.diff_page(old, [doc("record layouts", "2025-01-01")]) == ([], [])


def test_published_and_vstr():
    assert dd.published([doc("A v25-5", "x"), doc("B v26-7", "x"), doc("C", "x")]) == (26, 7)
    assert dd.published([doc("C", "x")]) is None
    assert dd.vstr((26, 7)) == "v26-7"


def test_conflicts_window_label_and_past():
    release = [["PSE", "2027-03-25"], ["Production", "2027-04-25"], ["Decommission", "2027-11-18"]]
    notices = {"a9809": [["PSE", "2027-03-25"], ["Production", "2027-04-15"], ["Decommission", "2027-11-17"]],
               "a9815": [["Production", "2026-11-19"]],
               "old": [["Production", "2026-05-01"]]}
    assert dd.conflicts(release, notices, "2026-10-06") == [
        ("Production", "2027-04-25", "2027-04-15", "a9809"),
        ("Decommission", "2027-11-18", "2027-11-17", "a9809"),
    ]
    assert dd.conflicts([["Production", "2026-05-20"]], notices, "2026-10-06") == []
