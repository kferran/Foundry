"""marketlib.http: one capped HTTPS GET with a fixed user agent and same-host redirects (spec §3.2, §4; M3, M4, M8)."""
import json
import urllib.request

import pytest

from marketlib import http


@pytest.fixture
def stub(tmp_path, monkeypatch):
    folder = tmp_path / "stub"
    folder.mkdir()
    monkeypatch.setenv("FOUNDRY_MARKET_STUB", str(folder))
    routes = {}

    def route(url, status=200, body=b"", location=""):
        name = f"r{len(routes)}"
        (folder / name).write_bytes(body)
        routes[url] = {"status": status, "file": name, "location": location}
        (folder / "routes.json").write_text(json.dumps(routes))
    route.folder = folder
    return route


def kind_of(url):
    with pytest.raises(http.MarketError) as err:
        http.get(url)
    return err.value


def test_a_200_returns_the_body(stub):
    stub("https://example.com/feed", body=b"<rss/>")
    assert http.get("https://example.com/feed") == b"<rss/>"


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth"), (429, "network"), (503, "network"),
                                         (404, "bad")])
def test_status_codes_map_to_kinds(stub, status, kind):
    stub("https://example.com/x", status=status)
    assert kind_of("https://example.com/x").kind == kind


def test_a_body_over_4_mb_is_bad(stub):
    stub("https://example.com/big", body=b"x" * (http.MAX_BYTES + 1))
    err = kind_of("https://example.com/big")
    assert err.kind == "bad" and "4 MB" in err.reason


def test_a_same_host_redirect_is_followed_and_another_host_is_refused(stub):
    stub("https://example.com/a", status=301, location="/b")
    stub("https://example.com/b", body=b"moved")
    assert http.get("https://example.com/a") == b"moved"
    stub("https://example.com/c", status=302, location="https://example.org/x")
    err = kind_of("https://example.com/c")
    assert err.kind == "bad" and "example.org" in err.reason
    stub("https://example.com/d", status=302, location="http://example.com/b")
    assert kind_of("https://example.com/d").kind == "bad"


def test_a_redirect_loop_stops(stub):
    stub("https://example.com/p", status=302, location="/q")
    stub("https://example.com/q", status=302, location="/p")
    assert kind_of("https://example.com/p").kind == "bad"


def test_a_non_https_url_is_refused_without_a_request(stub):
    assert kind_of("http://example.com/feed").kind == "bad"
    assert not (stub.folder / "requests.log").exists()


def test_the_request_sends_the_fixed_user_agent(monkeypatch):
    monkeypatch.delenv("FOUNDRY_MARKET_STUB", raising=False)
    seen = {}

    class Resp:
        status = 200

        def read(self, n=-1):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def open(self, req, timeout=None):
            seen["ua"] = req.get_header("User-agent")
            seen["timeout"] = timeout
            return Resp()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: Opener())
    assert http.get("https://example.com/feed") == b"ok"
    assert seen == {"ua": http.UA, "timeout": http.TIMEOUT}
    assert http.UA == "Mozilla/5.0 (compatible; foundry-market/1.0)"
