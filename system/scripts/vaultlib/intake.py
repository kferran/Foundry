"""Intake: compile inbox files and digest batches through run_headless.sh (spec §6.4)."""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import frontmatter, meetings, now as nowmod, publish, redact as redactmod, schema as schemamod

FRESH_SECONDS = 60
MAX_ATTEMPTS = 3
DIGEST_BATCH = 5
SKIP_SUFFIXES = ("~", ".tmp", ".swp", ".crdownload", ".part")
RAW_NAME = re.compile(r"^[A-Za-z0-9._ -]+$")
START, END = "#wiki-ingest-start", "#wiki-ingest-end"
NOTES = "## 📝 Notes"
BRIEFING_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
CAP_EXIT = 4
INVALID_INPUT_EXIT = 2
SETTINGS_EXIT = 3
SIGNAL_EXITS = (129, 130, 143)  # SIGHUP/SIGINT/SIGTERM: a stop or shutdown, not the input
NOT_INPUT_FAULT = (0, SETTINGS_EXIT, CAP_EXIT, 6, *SIGNAL_EXITS)  # 6 = busy lock
MEETING_PARTITIONS = ("work", "personal")
DROP_SUFFIXES = (".vtt", ".srt", ".txt", ".md")
DUPLICATE_SECONDS = 15 * 60


def _append_jsonl(path, record) -> None:
    """Append one JSON line; first terminate a torn last line so it cannot swallow this record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab+") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell():
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":
                fh.write(b"\n")
        fh.write((json.dumps(record) + "\n").encode("utf-8"))


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sanitize(name: str) -> str:
    cleaned = "".join(ch if (ch.isascii() and (ch.isalnum() or ch in "._ -")) else "_" for ch in name)
    cleaned = cleaned.lstrip(".")
    return cleaned or "file"


def unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    return path.with_name(f"{stem}-{time.time_ns()}{suffix}")


class Intake:
    def __init__(self, vault, now=None, max_runs=None):
        self.vault = Path(vault)
        offset = float(os.environ.get("INTAKE_NOW_OFFSET", "0"))
        self._now = now if now is not None else (time.time() + offset if offset else None)
        self.max_runs = max_runs if max_runs is not None else int(os.environ.get("INTAKE_MAX_RUNS", "5"))
        self.runs = 0
        self.logs = self.vault / "system" / "logs"
        try:
            self.tz = ZoneInfo(self.config("timezone", "UTC"))
        except (ZoneInfoNotFoundError, ValueError):
            self.tz = timezone.utc

    # -- helpers ---------------------------------------------------------
    def now(self) -> float:
        return self._now if self._now is not None else time.time()

    def dt(self) -> datetime:
        """Wall clock in the configured timezone (matches run_headless.sh's TZ)."""
        return datetime.now(self.tz)

    def today(self) -> str:
        return self.dt().strftime("%Y-%m-%d")

    def alert(self, message: str) -> None:
        self.logs.mkdir(parents=True, exist_ok=True)
        with open(self.logs / f"alerts_{self.today()}.md", "a", encoding="utf-8") as fh:
            fh.write(f"- {self.dt().strftime('%H:%M:%S')} [intake] {message}\n")

    def config(self, key: str, default: str) -> str:
        path = self.vault / "system" / "config.md"
        try:
            data = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
        except (OSError, UnicodeDecodeError):
            return default
        value = data.get(key)
        return value if isinstance(value, str) and value else default

    @contextlib.contextmanager
    def lock(self, name: str, timeout: float):
        """flock(2) on system/<name>; interoperates with flock(1) in run_headless.sh."""
        path = self.vault / "system" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as handle:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(name)
                    time.sleep(0.1)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def eligible(self, path: Path) -> bool:
        name = path.name
        try:
            if path.is_symlink() or not path.is_file() or name.startswith(".") or name.endswith(SKIP_SUFFIXES):
                return False
            if ".sync-conflict" in name:
                return False
            return self.now() - path.stat().st_mtime >= FRESH_SECONDS
        except OSError:
            return False  # vanished or unreadable

    def _jsonl(self, path: Path):
        if not path.is_file():
            return
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record

    def _ledgers(self):
        now = self.dt()
        first = now.replace(day=1)
        prev = (first.toordinal() - 1)
        prev_month = datetime.fromordinal(prev).strftime("%Y-%m")
        for month in (prev_month, now.strftime("%Y-%m")):
            yield from self._jsonl(self.logs / f"runs-{month}.jsonl")

    def failures_since_retry(self, sha: str) -> int:
        count = 0
        for record in self._ledgers():
            shas = record.get("input_sha256") or []
            if not isinstance(shas, list) or sha not in shas:
                continue
            if record.get("command") == "retry":
                count = 0
            else:
                code = record.get("exit")
                if isinstance(code, int) and not isinstance(code, bool) and code not in NOT_INPUT_FAULT:
                    count += 1
        return count

    def manifest_has(self, sha: str) -> bool:
        year = self.dt().year
        return any(r.get("sha256") == sha for y in (year - 1, year)
                   for r in self._jsonl(self.logs / f"intake_manifest-{y}.jsonl"))

    def manifest_add(self, sha: str, name: str) -> None:
        _append_jsonl(self.logs / f"intake_manifest-{self.dt().year}.jsonl",
                      {"sha256": sha, "name": name, "published_at": self.dt().isoformat()})

    def headless(self, rel_paths, shas) -> int:
        self.runs += 1
        env = {**os.environ, "FOUNDRY_ORIGINAL_SHA256": " ".join(shas)}
        return subprocess.run([str(self.vault / "system/scripts/run_headless.sh"), "ingest", *rel_paths],
                              cwd=self.vault, env=env).returncode

    def poison(self, path: Path, origin: str, sha: str, reason: str = "") -> None:
        dest = unique(self.vault / "system" / "quarantine" / "poisoned" / path.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
        (dest.parent / f"{dest.name}.origin.json").write_text(
            json.dumps({"origin": origin, "sha256": sha, "poisoned_at": self.dt().isoformat()}),
            encoding="utf-8")
        why = reason or f"after {MAX_ATTEMPTS} failed attempts"
        self.alert(f"poisoned {why}: {origin} → {dest.relative_to(self.vault)}")

    # -- briefing extraction ---------------------------------------------
    def extract_briefing(self) -> None:
        path = self.vault / "briefings" / f"{self.today()}.md"
        try:
            with self.lock("run.lock", timeout=600):
                self._extract_locked(path)
                self._extract_notes_locked()
        except TimeoutError:
            self.alert("briefing extraction skipped: run.lock busy")

    def _extract_notes_locked(self) -> None:
        """After midnight, send each earlier briefing's 📝 Notes blocks once (#61); the archive is never read."""
        record_path = self.logs / "extracted_blocks.jsonl"
        done = {r.get("briefing") for r in self._jsonl(record_path) if r.get("kind") == "notes"}
        for path in sorted((self.vault / "briefings").glob("*.md")):
            rel = path.relative_to(self.vault).as_posix()
            if not BRIEFING_NAME.match(path.name) or path.name[:10] >= self.today() or rel in done:
                continue
            if self._extract_locked(path, notes=True):
                _append_jsonl(record_path, {"kind": "notes", "briefing": rel,
                                            "time": self.dt().isoformat(timespec="seconds")})

    def _extract_locked(self, path: Path, notes: bool = False) -> bool:
        """Drop each new #wiki-ingest block; the briefing is never rewritten (two-machine spec §5.6).
        Blocks inside 📝 Notes wait for the end of the day (#61): notes=False sends the others, notes=True only
        those. True when the briefing was read and nothing blocked its blocks."""
        try:
            if not path.is_file():
                return False
            if self.now() - path.stat().st_mtime < FRESH_SECONDS:
                return False
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            self.alert(f"briefing {path.name} unreadable ({exc.__class__.__name__}); extraction skipped")
            return False
        if START not in text:
            return True
        blocks, current, problem, in_notes = [], None, "", False
        for line in text.split("\n"):
            stripped = line.strip()
            if current is None and line.startswith("## "):
                in_notes = stripped == NOTES
            if stripped == START:
                if current is not None:
                    problem = "has a nested #wiki-ingest-start"
                    current = None
                    break
                current, block_in_notes = [], in_notes
            elif stripped == END and current is not None:
                if block_in_notes == notes:
                    blocks.append(current)
                current = None
            elif current is not None:
                current.append(line)
        if current is not None:
            problem = "has an unterminated #wiki-ingest-start"
        if problem and notes:
            blocks = []  # a broken Notes section waits until it is fixed
        rel = path.relative_to(self.vault).as_posix()
        record_path = self.logs / "extracted_blocks.jsonl"
        known = {(r.get("briefing"), r.get("hash")) for r in self._jsonl(record_path) if r.get("kind") == "block"}
        try:
            for lines in blocks:
                body = "\n".join(lines)
                digest = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()
                if not body.strip() or (rel, digest) in known:
                    continue
                inbox = self.vault / "raw" / "inbox"
                inbox.mkdir(parents=True, exist_ok=True)
                drop = unique(inbox / f"daily_note_drop_{int(time.time())}.md")
                drop.write_text(body + "\n", encoding="utf-8")
                _append_jsonl(record_path, {"kind": "block", "briefing": rel, "hash": digest,
                                            "drop": drop.relative_to(self.vault).as_posix(),
                                            "time": self.dt().isoformat(timespec="seconds")})
                known.add((rel, digest))
        except OSError as exc:
            self.alert(f"briefing extraction failed ({exc.__class__.__name__}); will retry")
            return False
        if problem:
            day = self.today()
            seen = any(r.get("kind") == "alert" and r.get("briefing") == rel and r.get("reason") == problem
                       and r.get("date") == day for r in self._jsonl(record_path))
            if not seen:
                self.alert(f"briefing {path.name} {problem}; the blocks after it wait until it is fixed")
                _append_jsonl(record_path, {"kind": "alert", "briefing": rel, "reason": problem, "date": day})
        return not problem

    # -- the Now page (Now page spec §3.4) -------------------------------
    def check_now(self) -> None:
        """Close Now lines on checked evidence; a busy run.lock skips this tick."""
        try:
            with self.lock("run.lock", timeout=0):
                nowmod.check(self.vault, self.today(), self.alert)
        except TimeoutError:
            pass

    # -- inbox -----------------------------------------------------------
    def process_inbox(self) -> bool:
        inbox = self.vault / "raw" / "inbox"
        if not inbox.is_dir():
            return True
        ready = []
        for p in inbox.iterdir():
            if self.eligible(p):
                try:
                    ready.append((p.stat().st_mtime, p.name, p))
                except OSError:
                    continue
        for _, _, path in sorted(ready):
            if self.runs >= self.max_runs:
                return True
            try:
                if not self._inbox_file(path):
                    return False
            except OSError as exc:
                self.alert(f"skipped raw/inbox/{path.name}: {exc.__class__.__name__}: {exc}")
        return True

    def _inbox_file(self, path: Path) -> bool:
        archive, telemetry = self.vault / "raw" / "archive", self.vault / "raw" / "telemetry"
        if not RAW_NAME.match(path.name):
            renamed = unique(path.with_name(sanitize(path.name)))
            path.rename(renamed)
            path = renamed
        sha = sha256_file(path)
        if self.manifest_has(sha):
            archive.mkdir(parents=True, exist_ok=True)
            path.rename(unique(archive / f"{path.stem}-dup-{int(time.time())}{path.suffix}"))
            return True
        if path.suffix == ".md":
            data = frontmatter.parse(path.read_text(encoding="utf-8", errors="replace")).data or {}
            if data.get("type") == "production_error":
                telemetry.mkdir(parents=True, exist_ok=True)
                path.rename(unique(telemetry / path.name))
                return True
        if (archive / path.name).exists():
            renamed = path.with_name(f"{path.stem}-{int(time.time())}{path.suffix}")
            path.rename(renamed)
            path = renamed
        staging = self.vault / "raw" / "inbox" / ".staging"
        staging.mkdir(parents=True, exist_ok=True)
        copy = staging / path.name
        raw = path.read_bytes()
        text, _ = redactmod.redact(raw.decode("utf-8", errors="replace"))
        copy.write_text(text, encoding="utf-8")
        try:
            rc = self.headless([copy.relative_to(self.vault).as_posix()], [sha])
        finally:
            copy.unlink(missing_ok=True)
        if rc == 0:
            # manifest first: if the archive rename then fails, the next run archives it as a dup
            self.manifest_add(sha, path.name)
            archive.mkdir(parents=True, exist_ok=True)
            path.rename(unique(archive / path.name))
            return True
        if rc in (CAP_EXIT, SETTINGS_EXIT):
            return False  # cap or invalid settings: every later run would fail too
        if rc == INVALID_INPUT_EXIT:
            # run_headless.sh rejects before any ledger line, so attempts would never advance
            self.poison(path, f"raw/inbox/{path.name}", sha, reason="immediately, rejected as invalid input (exit 2)")
            return True
        if self.failures_since_retry(sha) >= MAX_ATTEMPTS:
            self.poison(path, f"raw/inbox/{path.name}", sha)
        else:
            self.alert(f"ingest of raw/inbox/{path.name} failed (exit {rc}); will retry")
        return True

    # -- digests ---------------------------------------------------------
    def _solo(self) -> set:
        try:
            return set(json.loads((self.logs / "intake_solo.json").read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError):
            return set()

    def _save_solo(self, shas: set) -> None:
        self.logs.mkdir(parents=True, exist_ok=True)
        (self.logs / "intake_solo.json").write_text(json.dumps(sorted(shas)), encoding="utf-8")

    def _pending_digests(self, notes: Path, attempted: set) -> dict:
        """Eligible, not-yet-attempted digests in mtime order, mapped to their hashes."""
        found = []
        for p in notes.iterdir():
            if p.suffix != ".md" or p in attempted or not self.eligible(p):
                continue
            try:
                found.append((p.stat().st_mtime, p.name, p, sha256_file(p)))
            except OSError as exc:
                attempted.add(p)
                self.alert(f"skipped {p.relative_to(self.vault).as_posix()}: {exc.__class__.__name__}: {exc}")
        return {p: sha for _, _, p, sha in sorted(found, key=lambda t: t[:2])}

    def process_digests(self) -> bool:
        attempted: set = set()
        progress = True
        while progress:
            progress = False
            for partition in schemamod.PARTITIONS:
                if self.runs >= self.max_runs:
                    return True
                notes = self.vault / "raw" / partition / "notes"
                if not notes.is_dir():
                    continue
                shas = self._pending_digests(notes, attempted)
                if not shas:
                    continue
                solo = self._solo()
                pending = list(shas)
                first = pending[0]
                batch = [first] if shas[first] in solo else [p for p in pending if shas[p] not in solo][:DIGEST_BATCH]
                attempted.update(batch)
                progress = True
                rc = self.headless([p.relative_to(self.vault).as_posix() for p in batch], [shas[p] for p in batch])
                if rc == 0:
                    self._archive_batch(partition, batch, shas, solo)
                elif rc in (CAP_EXIT, SETTINGS_EXIT):
                    return False  # cap or invalid settings: every later run would fail too
                elif len(batch) > 1:
                    # includes rc 2: one bad name must not poison its batch-mates
                    self._save_solo(solo | {shas[p] for p in batch})
                    self.alert(f"digest batch in {partition} failed (exit {rc}); retrying one at a time")
                else:
                    self._solo_failure(partition, first, shas[first], rc)
        return True

    def _archive_batch(self, partition: str, batch, shas: dict, solo: set) -> None:
        archive = self.vault / "raw" / partition / "archive"
        done = set()
        for p in batch:
            try:
                archive.mkdir(parents=True, exist_ok=True)
                p.rename(unique(archive / p.name))
                done.add(shas[p])
            except OSError as exc:
                self.alert(f"could not archive raw/{partition}/notes/{p.name}: {exc.__class__.__name__}: {exc}")
        self._save_solo(solo - done)

    def _solo_failure(self, partition: str, path: Path, sha: str, rc: int) -> None:
        origin = f"raw/{partition}/notes/{path.name}"
        try:
            if rc == INVALID_INPUT_EXIT:
                # run_headless.sh rejects before any ledger line, so attempts would never advance
                self.poison(path, origin, sha, reason="immediately, rejected as invalid input (exit 2)")
            elif self.failures_since_retry(sha) >= MAX_ATTEMPTS:
                self.poison(path, origin, sha)
            else:
                self.alert(f"digest {origin} failed (exit {rc}); will retry")
        except OSError as exc:
            self.alert(f"skipped {origin}: {exc.__class__.__name__}: {exc}")

    # -- meetings (meetings spec §2.3) -------------------------------------
    def import_meetings(self) -> None:
        """Import fetched Docs and dropped transcripts, each as its own meeting run, under run.lock (no wait)."""
        if self.config("machine_role", "standalone") == "client":
            return
        self._readd_meeting_inputs()
        sources = self._meeting_sources()
        if not sources:
            return
        try:
            with self.lock("run.lock", timeout=0):
                failed = publish.recover(self.vault).get("failed") or []
                if failed:
                    self.alert(f"publish recovery failed for run(s): {' '.join(failed)}")
                for path in sources:
                    rel = path.relative_to(self.vault).as_posix()
                    try:
                        self._import_meeting(path, rel)
                    except meetings.ParseError as exc:
                        self._quarantine_meeting(path, rel, str(exc))
                    except Exception as exc:  # noqa: BLE001 - one source must not stop the others
                        self._meeting_failure(path, rel, exc)
        except TimeoutError:
            pass  # a run holds the lock: the sources wait for the next tick

    def _meeting_sources(self) -> list:
        found = sorted((self.vault / "raw" / "meetings").glob("*.gdoc.md"))
        drop = self.vault / "meetings" / "drop"
        if drop.is_dir():  # every subfolder: a file outside work/ and personal/ is quarantined
            found += sorted(p for p in drop.rglob("*") if self.eligible(p)
                            and not any(part.startswith(".") for part in p.relative_to(drop).parts))
        return found

    def _meeting_failure(self, path: Path, rel: str, exc: Exception) -> None:
        """Log a failed import; the third failure of the same file quarantines it."""
        reason = f"{exc.__class__.__name__}: {exc}"
        try:
            digest = sha256_file(path)
        except OSError:
            digest = ""
        self._meeting_log({"kind": "failed", "source": rel, "sha256": digest, "reason": reason})
        count = sum(1 for log in sorted(self.logs.glob("meetings-*.jsonl"))[-2:] for r in self._jsonl(log)
                    if r.get("kind") == "failed" and r.get("source") == rel and r.get("sha256") == digest)
        if count >= MAX_ATTEMPTS and path.exists():
            self._quarantine_meeting(path, rel, f"the import failed {count} times; the last error: {reason}")
        else:
            self.alert(f"meeting import of {rel} failed ({reason}); will retry")

    def _meeting_log(self, record) -> None:
        _append_jsonl(self.logs / f"meetings-{self.dt():%Y-%m}.jsonl",
                      {"time": self.dt().isoformat(timespec="seconds"), **record})

    def _quarantine_meeting(self, path: Path, rel: str, reason: str) -> None:
        dest = unique(self.vault / "system" / "quarantine" / "meetings" / path.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
        dest.with_name(dest.name + ".reason.txt").write_text(reason + "\n", encoding="utf-8")
        self.alert(f"meeting source {rel} quarantined: {reason}")
        self._meeting_log({"kind": "quarantined", "source": rel, "file": dest.name, "reason": reason})

    def _commit_time(self, rel: str):
        try:
            out = subprocess.run(["git", "-C", str(self.vault), "log", "-1", "--format=%cI", "--", rel],
                                 capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return out.stdout.strip() or None

    def _parse_meeting(self, path: Path, rel: str):
        """(meeting, partition) for one source; raises meetings.ParseError for a bad one."""
        if rel.startswith("raw/meetings/"):
            partition = self.config("meetings_partition", "")
            if partition not in MEETING_PARTITIONS:
                partition = self.config("default_partition", "personal")
            if partition not in MEETING_PARTITIONS:
                partition = "personal"
            return meetings.parse_gdoc(path.read_text(encoding="utf-8", errors="replace"), self.tz), partition
        partition = path.parent.name
        if partition not in MEETING_PARTITIONS or path.parent.parent != self.vault / "meetings" / "drop":
            raise meetings.ParseError("not in a partition folder (meetings/drop/work/ or meetings/drop/personal/)")
        if path.suffix.lower() not in DROP_SUFFIXES:
            raise meetings.ParseError(f"not a transcript file type ({', '.join(DROP_SUFFIXES)})")
        data = path.read_bytes()
        start = meetings.drop_start(path.name, self._commit_time(rel), path.stat().st_mtime, self.tz)
        m = meetings.parse_drop(path.name, data, self.tz, start)
        m.source = f"drop:{hashlib.sha256(data).hexdigest()}"
        return m, partition

    def _meeting_notes(self) -> list:
        """(path, frontmatter) of every meeting note on disk, deprecated ones included."""
        out = []
        for path in sorted((self.vault / "wiki").glob("*/meetings/*.md")):
            if path.name.endswith(".transcript.md"):
                continue
            try:
                data = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
            except (OSError, UnicodeDecodeError):
                continue
            if data.get("type") == "meeting":
                out.append((path, data))
        return out

    def _import_meeting(self, path: Path, rel: str) -> None:
        m, partition = self._parse_meeting(path, rel)
        m = meetings.scrub(m)
        known = self._meeting_notes()
        same = next((p for p, d in known if d.get("source") == m.source), None)
        if same is not None:  # published by an earlier tick: finish its hand-off
            name, partition = same.name[:-3], same.parent.parent.name
            note = f"wiki/{partition}/meetings/{name}.md"
            if not any(r.get("kind") == "imported" and r.get("note") == note
                       for log in sorted(self.logs.glob("meetings-*.jsonl"))[-2:] for r in self._jsonl(log)):
                # that tick stopped before its log line (#43): the brief's Notices read complete from it
                self._meeting_log({"kind": "imported", "source": rel, "note": note, "complete": m.complete})
        else:
            twin = next((p for p, d in known if self._same_meeting(m, d)), None)
            if twin is not None:
                self._archive_duplicate(path, rel, m, twin)
                return
            name = self._free_name(meetings.note_name(m))
            report = self._publish_meeting(m, name, partition, rel)
            if report["status"] == "conflict":  # held back at apply time (#37): the next tick finishes or retries
                self.alert(f"meeting import of {rel} held back {', '.join(report['conflicts'])} "
                           "(changed during the publish); will retry")
                return
            if report["status"] != "published":
                problems = [p["reason"] for p in report.get("problems") or []]
                if problems and all(r.startswith("conflict:") for r in problems):
                    return  # a target appeared meanwhile: the next tick's duplicate check finds it
                self._quarantine_meeting(path, rel, "the publish gate rejected it: " + "; ".join(problems))
                return
            self._meeting_log({"kind": "imported", "source": rel, "note": f"wiki/{partition}/meetings/{name}.md",
                               "complete": m.complete})
        self._hand_to_compile(m, name, partition)
        path.unlink()

    def _same_meeting(self, m, data) -> bool:
        if m.source.startswith("gdoc:") and str(data.get("source", "")).startswith("gdoc:"):
            return False  # one Gemini Doc per meeting (spec §1.1): two Docs are two meetings
        try:
            start = datetime.fromisoformat(str(data.get("start")))
            if start.tzinfo is None:  # the schema allows a start without an offset: it is local time
                start = start.replace(tzinfo=self.tz)
        except (ValueError, TypeError):
            return False
        return (meetings.slug(str(data.get("title", ""))) == meetings.slug(m.title)
                and abs((start - m.start).total_seconds()) <= DUPLICATE_SECONDS)

    def _archive_duplicate(self, path: Path, rel: str, m, twin: Path) -> None:
        archive = self.vault / "raw" / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        path.rename(unique(archive / path.name))
        note = twin.relative_to(self.vault).as_posix()
        self.alert(f"meeting source {rel} archived: the same meeting is already {note} (first source wins)")
        self._meeting_log({"kind": "duplicate", "source": rel, "note": note})
        if m.source.startswith("gdoc:"):
            _append_jsonl(self.logs / f"meetings_fetch-{self.dt():%Y-%m}.jsonl",
                          {"time": self.dt().isoformat(timespec="seconds"), "step": "import",
                           "doc": m.source[5:], "exit": 0, "reason": f"duplicate of {note}", "skipped": True})

    def _free_name(self, name: str) -> str:
        taken = {p.name for p in (self.vault / "wiki").glob("*/meetings/*.md")}
        candidate, n = name, 1
        while f"{candidate}.md" in taken or f"{candidate}.transcript.md" in taken:
            n += 1
            candidate = f"{name}-{n}"
        return candidate

    def _publish_meeting(self, m, name: str, partition: str, rel: str) -> dict:
        run_id = f"{self.dt():%Y%m%dT%H%M%S}-meeting-{os.urandom(2).hex()}"
        base = f"wiki/{partition}/meetings/{name}"
        targets = [f"{base}.md", f"{base}.transcript.md"]
        started = self.dt().isoformat(timespec="seconds")
        publish.snapshot(self.vault, run_id, targets)
        staging = publish.staging_dir(self.vault, run_id)
        for target, text in zip(targets, (meetings.render_meeting(m, name, partition),
                                          meetings.render_transcript(m, name, partition))):
            (staging / target).parent.mkdir(parents=True, exist_ok=True)
            (staging / target).write_text(text, encoding="utf-8")
        report = publish.commit_run(self.vault, run_id)
        _append_jsonl(self.logs / f"runs-{run_id[:4]}-{run_id[4:6]}.jsonl", {
            "run_id": run_id, "command": "meeting", "started_at": started,
            "finished_at": self.dt().isoformat(timespec="seconds"), "inputs": [rel], "input_sha256": [],
            "partition": partition, "exit": 0 if report["status"] == "published" else 5,
            "publish": {"status": report["status"], "published": report.get("published") or [],
                        "rejected": sorted({p["path"] for p in report.get("problems") or []}),
                        "conflicts": report.get("conflicts") or []}})
        return report

    def _hand_to_compile(self, m, name: str, partition: str) -> None:
        notes = self.vault / "raw" / partition / "notes"
        prefix = f"{name}.meeting-input"
        for folder in (notes, self.vault / "raw" / partition / "archive",
                       self.vault / "system" / "quarantine" / "poisoned"):
            if folder.is_dir() and any(p.name.startswith(prefix) for p in folder.iterdir()):
                return
        notes.mkdir(parents=True, exist_ok=True)
        tmp = notes / f".{prefix}.tmp"
        tmp.write_text(meetings.render_input(m, name, partition, self.dt()), encoding="utf-8")
        self._save_solo(self._solo() | {sha256_file(tmp)})
        os.replace(tmp, notes / f"{prefix}.md")

    def _readd_meeting_inputs(self) -> None:
        """A meeting input restored by --retry lost its solo flag: give it back."""
        shas = set()
        for partition in MEETING_PARTITIONS:
            for path in (self.vault / "raw" / partition / "notes").glob("*.md"):
                try:
                    if (frontmatter.parse(path.read_text(encoding="utf-8")).data or {}).get("type") == "meeting_input":
                        shas.add(sha256_file(path))
                except (OSError, UnicodeDecodeError):
                    continue
        solo = self._solo()
        if not shas <= solo:
            self._save_solo(solo | shas)

    # -- retry -----------------------------------------------------------
    def retry(self, run_id=None) -> list:
        poisoned = self.vault / "system" / "quarantine" / "poisoned"
        if not poisoned.is_dir():
            return []
        wanted = None
        if run_id is not None:
            wanted = set()
            for record in self._ledgers():
                if record.get("run_id") == run_id and isinstance(record.get("input_sha256"), list):
                    wanted.update(record["input_sha256"])
        restored, shas = [], []
        for sidecar in sorted(poisoned.glob("*.origin.json")):
            try:
                info = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(info, dict) or (wanted is not None and info.get("sha256") not in wanted):
                continue
            item = poisoned / sidecar.name[: -len(".origin.json")]
            origin = info.get("origin", "")
            if (not item.is_file() or not isinstance(origin, str)
                    or not re.match(r"^raw/(inbox|work/notes|personal/notes|shared/notes)/[^/]+$", origin)):
                continue
            try:
                dest = unique(self.vault / origin)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(dest))
            except OSError as exc:
                self.alert(f"retry skipped {origin}: {exc.__class__.__name__}: {exc}")
                continue
            restored.append(dest.relative_to(self.vault).as_posix())
            shas.append(info.get("sha256"))
            try:
                sidecar.unlink()
            except OSError as exc:
                self.alert(f"retry restored {origin} but its sidecar {sidecar.name} remains: "
                           f"{exc.__class__.__name__}: {exc}")
        if restored:
            try:
                self._save_solo(self._solo() - set(shas))
            except OSError as exc:
                self.alert(f"retry could not update the solo list: {exc.__class__.__name__}: {exc}")
            _append_jsonl(self.logs / f"runs-{self.dt().strftime('%Y-%m')}.jsonl",
                          {"run_id": f"retry-{int(time.time())}", "command": "retry",
                           "started_at": self.dt().isoformat(),
                           "inputs": restored, "input_sha256": shas, "exit": 0})
        return restored

    def run(self) -> None:
        try:
            with self.lock("intake.lock", timeout=0):
                self.extract_briefing()
                try:
                    self.check_now()
                except Exception as exc:  # noqa: BLE001 - meetings, inbox and digests still run
                    self.alert(f"Now check failed ({exc.__class__.__name__}: {exc}); will retry")
                try:
                    self.import_meetings()
                except Exception as exc:  # noqa: BLE001 - inbox and digests still run
                    self.alert(f"meeting import failed ({exc.__class__.__name__}: {exc}); will retry")
                if self.process_inbox():
                    self.process_digests()
        except TimeoutError:
            pass  # another daemon is running
