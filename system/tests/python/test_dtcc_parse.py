from helpers import REPO
from vaultlib import dtcc_parse as dp

FX = REPO / "system" / "tests" / "fixtures" / "dtcc"


def fx(name):
    return (FX / name).read_text(encoding="utf-8")


def test_parse_date_forms():
    assert dp.parse_date("March 25th 2027") == "2027-03-25"
    assert dp.parse_date("AUGUST 12TH 2026") == "2026-08-12"
    assert dp.parse_date("April 08, 2026") == "2026-04-08"
    assert dp.parse_date("08/20/2026") == "2026-08-20"
    assert dp.parse_date("07/02/26") == "2026-07-02"
    assert dp.parse_date("2027-11-18") == "2027-11-18"
    assert dp.parse_date("February 30, 2027") is None
    assert dp.parse_date("") is None


def test_page_docs_keep_dated_cards_only():
    docs = dp.page_docs(fx("app-sub.html"))
    assert [(d["section"], d["title"], d["date"]) for d in docs] == [
        ("Application & Subsequent Premium", "I&RS App/Sub Record Layouts v26-7", "2026-04-08"),
        ("Application & Subsequent Premium", "Record Layouts", "2024-07-01"),
        ("Subsequent Premium", "Record Layouts", "2025-03-02"),
    ]


def test_same_title_in_two_sections_is_two_docs():
    docs = dp.page_docs(fx("app-sub.html"))
    assert len({(dp.norm(d["section"]), dp.norm(d["title"])) for d in docs}) == 3


def test_non_card_page_has_no_docs():
    assert dp.page_docs(fx("record-layouts.html")) == []


def test_version_of():
    assert dp.version_of("I&RS STL Record Layouts v26-7") == (26, 7)
    assert dp.version_of("POV Layouts V26-10") == (26, 10)
    assert dp.version_of("Record Layouts") is None


def test_release_block_dates():
    blk = dp.release_block(fx("irs-current-enhancements-release.html"))
    assert blk["dates"] == [["PSE", "2027-03-25"], ["Production", "2027-04-25"], ["Decommission", "2027-11-18"]]
    assert len(blk["hash"]) == 16
    assert dp.release_block("<p>nothing here</p>") is None


def test_milestones_from_notice_text():
    flat = " ".join(fx("p9809").split())
    assert dp.milestones(flat) == [("PSE", "2027-03-25"), ("Production", "2027-04-15"), ("Decommission", "2027-11-17")]
    flat = " ".join(fx("p9815").split())
    assert dp.milestones(flat) == [("Test", "2026-10-29"), ("Test", "2026-11-12"), ("Production", "2026-11-19")]


def test_rss_dedupes_and_keeps_the_copy_with_a_summary():
    items = dp.rss_items(fx("all-important-notices.xml"))
    assert [i["number"] for i in items] == ["a9809", "a9815", "24453-26"]
    assert items[0]["summary"] == "DTCC I&RS DOCUMENT PROCESSING API IMPLEMENTATION TIMELINE"
    assert items[0]["link"] == "https://files.dtcc.com/download/assets/a9809/p9809"


def test_pdf_header():
    h = dp.pdf_header(fx("p9815"))
    assert h == {"category": "INSURANCE & RETIREMENT SOLUTIONS", "to": "ALL MEMBERS AND LIMITED MEMBERS",
                 "subject": "I&RS FALL 2026 ENHANCEMENT RELEASE"}
    assert dp.pdf_header(fx("p9809"))["subject"] == ""


def test_codes_in_whole_words_only():
    text = "Subject: ATTENTION. This release impacts the following services: STL, PAR and RPL"
    assert dp.codes_in(text, ["ATT", "STL", "PAR", "RPL", "SUB"]) == ["STL", "PAR", "RPL"]


def test_catalog():
    assert dp.catalog(fx("viewAssetsGrid.html")) == [
        {"name": "ACATS: Account Transfer", "published": "2026-07-02", "version": "1.0.0"},
        {"name": "Insurance Information Exchange (IIEX)", "published": "", "version": ""},
        {"name": "Profile Management: OAuth2", "published": "2025-04-21", "version": "1.0.3"},
    ]


def test_matches():
    kws = [r"\bI&RS\b", r"\binsurance\b", r"\bannuit"]
    assert dp.matches(kws, "x", "Annuity data")
    assert not dp.matches(kws, "Depositary Fees Notification", "")
