"""Network seam for the DTCC watcher (spec §2): allowlisted hosts, polite pacing, stub-able by FOUNDRY_DTCC_STUB."""
import http.cookiejar
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOSTS = {"dtcclearning.com", "www.dtcc.com", "files.dtcc.com", "developer.dtcc.com"}
BASE = "https://dtcclearning.com/products-and-services/insurance-retirement-services/"
RELEASE = BASE + "irs-current-enhancements-release.html"
RSS = "https://www.dtcc.com/rss-feeds/legal/all-important-notices.xml"
MARKET = "https://developer.dtcc.com/"
UA = "Mozilla/5.0 (X11; Linux x86_64) foundry-dtcc-watch/1"
TIMEOUT = 30


class FetchError(Exception):
    pass


class PdfUnavailable(Exception):
    pass


def allowed(url: str) -> bool:
    u = urllib.parse.urlparse(url or "")
    return u.scheme == "https" and u.hostname in HOSTS


class Fetcher:
    def __init__(self):
        self.stub = os.environ.get("FOUNDRY_DTCC_STUB")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.last = 0.0

    def get(self, url: str) -> bytes:
        if not allowed(url):
            raise FetchError(f"host not allowed: {url}")
        if self.stub:
            name = urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1] or "index"
            path = Path(self.stub) / name
            if not path.is_file():
                raise FetchError(f"no stub for {name}")
            return path.read_bytes()
        time.sleep(max(0.0, self.last + 1.0 - time.monotonic()))
        self.last = time.monotonic()
        try:
            with self.opener.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=TIMEOUT) as resp:
                return resp.read()
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
            raise FetchError(f"{urllib.parse.urlparse(url).path}: {exc}") from None

    def text(self, url: str) -> str:
        return self.get(url).decode("utf-8", "replace")

    def catalog(self) -> str:
        if not self.stub:  # the grid is empty without the session the first two requests set up
            self.get(MARKET)
            self.get(MARKET + "home/view.html")
        return self.text(MARKET + "inventory/viewAssetsGrid.html")

    def pdf_text(self, url: str) -> str:
        if self.stub:
            return self.text(url)
        if not shutil.which("pdftotext"):
            raise PdfUnavailable("pdftotext is not installed (poppler-utils)")
        data = self.get(url)
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(data)
            f.flush()
            r = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, timeout=60)
        if r.returncode != 0:
            raise PdfUnavailable(f"pdftotext exit {r.returncode}")
        return r.stdout.decode("utf-8", "replace")
