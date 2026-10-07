import pytest

from helpers import REPO
from vaultlib import dtcc_fetch as df

FX = REPO / "system" / "tests" / "fixtures" / "dtcc"


def test_allowed_hosts():
    assert df.allowed("https://files.dtcc.com/download/assets/a/b")
    assert df.allowed(df.RSS) and df.allowed(df.RELEASE) and df.allowed(df.MARKET)
    assert not df.allowed("http://www.dtcc.com/x")
    assert not df.allowed("https://evil.example.com/x")
    assert not df.allowed("https://www.dtcc.com.evil.example/x")


def test_stub_reads_last_segment(monkeypatch):
    monkeypatch.setenv("FOUNDRY_DTCC_STUB", str(FX))
    f = df.Fetcher()
    assert "card__title" in f.text(df.BASE + "app-sub.html")
    assert "assetCard" in f.catalog()
    assert "Category:" in f.pdf_text("https://files.dtcc.com/download/assets/a9815/p9815")
    with pytest.raises(df.FetchError):
        f.text(df.BASE + "missing.html")
    with pytest.raises(df.FetchError):
        f.text("https://evil.example.com/app-sub.html")
