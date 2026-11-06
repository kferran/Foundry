"""One capped HTTPS GET for the market fetch (market watch spec §3.2, §4): a fixed user agent that names the client,
a 30-second timeout, a 4 MB cap, and redirects only to the same host over HTTPS. Tests set FOUNDRY_MARKET_STUB to a
folder holding routes.json ({url: {status, file, location}}); each requested URL is appended to its requests.log."""
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; foundry-market/1.0)"
TIMEOUT = 30
MAX_BYTES = 4 * 1024 * 1024
MAX_HOPS = 5
REDIRECTS = (301, 302, 303, 307, 308)


class MarketError(Exception):
    def __init__(self, kind: str, reason: str):
        super().__init__(f"{kind}: {reason}")
        self.kind, self.reason = kind, reason


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).hostname or ""


def _check_url(url: str, origin: str = "") -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise MarketError("bad", f"not an https URL: {url}" if not origin else f"redirect to {url} is not https")
    if origin and parts.hostname != origin:
        raise MarketError("bad", f"redirect to another host: {parts.hostname}")


def _status(code: int, url: str) -> MarketError:
    if code in (401, 403):
        return MarketError("auth", f"HTTP {code} from {_host(url)}")
    if code == 429 or code >= 500:
        return MarketError("network", f"HTTP {code} from {_host(url)}")
    return MarketError("bad", f"HTTP {code} from {_host(url)}")


def _capped(body: bytes, url: str) -> bytes:
    if len(body) > MAX_BYTES:
        raise MarketError("bad", f"{_host(url)}: response over 4 MB")
    return body


class _SameHost(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_HOPS

    def __init__(self, origin: str):
        self.origin = origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl, self.origin)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _stub(folder: str, url: str) -> bytes:
    routes = json.loads((open(os.path.join(folder, "routes.json"), encoding="utf-8")).read())
    origin = _host(url)
    for _ in range(MAX_HOPS + 1):
        with open(os.path.join(folder, "requests.log"), "a", encoding="utf-8") as log:
            log.write(url + "\n")
        r = routes.get(url) or {"status": 404, "file": "", "location": ""}
        if r["status"] in REDIRECTS:
            url = urllib.parse.urljoin(url, r["location"])
            _check_url(url, origin)
            continue
        if r["status"] != 200:
            raise _status(r["status"], url)
        with open(os.path.join(folder, r["file"]), "rb") as fh:
            return _capped(fh.read(MAX_BYTES + 1), url)
    raise MarketError("bad", f"{origin}: more than {MAX_HOPS} redirects")


def get(url: str) -> bytes:
    """The body at url, or MarketError with kind auth, network, timeout or bad."""
    _check_url(url)
    folder = os.environ.get("FOUNDRY_MARKET_STUB")
    if folder:
        return _stub(folder, url)
    opener = urllib.request.build_opener(_SameHost(_host(url)))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            return _capped(resp.read(MAX_BYTES + 1), url)
    except MarketError:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code in REDIRECTS:  # the handler gave up: too many hops
            raise MarketError("bad", f"{_host(url)}: more than {MAX_HOPS} redirects") from None
        raise _status(exc.code, url) from None
    except (socket.timeout, TimeoutError):
        raise MarketError("timeout", f"{_host(url)}: no answer in {TIMEOUT} s") from None
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise MarketError("timeout", f"{_host(url)}: no answer in {TIMEOUT} s") from None
        raise MarketError("network", f"{_host(url)}: {type(reason).__name__}") from None
