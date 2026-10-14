# Transcript drops: the committed drop is the redacted drop

**Date:** 2026-10-13
**Status:** Accepted 2026-10-14 (owner: the hook may rewrite a dropped file).
**Issue:** #136 (S6). From the 2026-10-13 audit (`docs/superpowers/2026-10-13-audit.md` on the audit branch).

## 1. Problem

A transcript dropped into `meetings/drop/<partition>/` on a client reaches the server through git: the Obsidian Git plugin commits and pushes it, the server syncs, imports it and deletes the file (meetings spec §2.2, §2.3 step 8). The pre-commit hook refuses a drop with a wrong extension or one a named detector fires on (`redact.py --kinds`); the generic high-entropy detector was left out because transcript cue IDs trip it. The server redacts the parsed meeting with the full `redact()` (`meetings._clean`) before it publishes the note and the transcript. So the blob pushed to `origin` holds everything the published transcript later redacts (a high-entropy string, a spoken `password: x`), and it stays in `origin`'s history after the import deletes the file. A UTF-16 drop, which the import accepts (#41), is decoded as UTF-8 by `redact.py`, so the hook's check reads it as noise today.

## 2. Decisions

- **The hook rewrites the drop instead of refusing it.** For each staged transcript it runs the staged blob through `redact.py --drop`, writes the result to the working file, re-adds it, and prints `pre-commit: redacted N in <file>` when N is above zero. What is committed is the text the import would redact anyway, so the blob in history holds nothing the published transcript does not. The extension refusal stays. Why a rewrite: gitignoring the drops removes a client's only channel to the server (meetings spec §1), and refusing on the full detector set would refuse every Teams transcript on its cue IDs.
- **`redact.py --drop`** decodes stdin as the import does (`meetings.decode`, today `_decode`: UTF-8 with or without a byte-order mark, UTF-16 with one) and writes UTF-8 through the full `redact()`. A drop the decoder rejects (NULs after decoding) is refused by the hook with the import's own reason, since the import would quarantine it. `--kinds` and `named_kinds()` go, with their tests: nothing else calls them.
- **The working file is rewritten along with the index blob.** A blob-only rewrite leaves the working tree differing from the index, and Obsidian Git re-stages the raw file every cycle. The owner loses the raw copy on the client; the import deletes the drop anyway. **Revised 2026-10-14 (review):** the rewrite requires the working copy to equal the index blob (`git diff --quiet -- <file>`); a partly staged drop is refused with "stage the whole file", so an empty staged blob never overwrites text pasted in later. A symlink is refused too ("not a regular file"), so the rewrite never follows a link out of the repository.
- A high-entropy cue ID becomes `[REDACTED:high_entropy]` in the committed VTT. A cue identifier is any line without `-->`, so the import still parses it, and `drop:<sha256>` is computed from the committed bytes on every machine alike.
- **Owner decision:** the hook may rewrite a file the owner just dropped. Recommendation: yes; the other two fixes keep the finding open or break the client channel.

## 3. Changes

- `.githooks/pre-commit`: the rewrite loop replaces the `--kinds` check (`git cat-file blob` → `redact.py --drop` → write the file → `git add`).
- `system/scripts/redact.py`: `--drop`. `vaultlib/redact.py`: `named_kinds` removed. `vaultlib/meetings.py`: `_decode` becomes `decode`.
- `FOUNDRY.md`: the Client paragraph and the layout line for `meetings/drop/` say the hook redacts a drop when it is committed; the Security model's secrets bullet likewise. `docs/superpowers/specs/2026-10-05-meetings-design.md` §2.2 and its risk table get a dated note pointing here.

**Existing vault:** nothing to install (`setup_remote.sh` already sets `core.hooksPath`). Drops already in history stay there.

## 4. Tests

bats `meetings.bats`: the named-secret case flips: `call.txt` with an AWS key and `token = hunter2` commits with exit 0, the committed blob and the working file both read `[REDACTED:aws_key]` and `[REDACTED:assignment]`, and the output names the count; the Teams-style VTT commits with its cue ID redacted and intake then imports it as one turn; a UTF-16 drop with a byte-order mark commits as UTF-8 text with its secret redacted; `slides.pdf` is still refused; `.gitkeep` still commits; the spoken-password case flips too: `api_key = …` commits redacted, and `password: it expired` commits as `password: [REDACTED:assignment] expired`, the text the published transcript carries today. pytest `test_redact.py`: `--drop` on UTF-8 input, UTF-8 with a mark and UTF-16; the four `named_kinds` and `--kinds` cases go. Each fails before the change. Bound tools: bats, pytest and the gate.

## 5. Out of scope

- Mobile drops (Obsidian mobile runs no hooks): guarded by the server's redaction only, as before.
- Rewriting `origin`'s history for drops already pushed.
- ~~Drive-link stripping in the hook~~ **Revised 2026-10-14 (review):** `--drop` runs the import's `meetings.strip_drive` before `redact()`. Redacting the raw text ate part of a Drive URL, so `DRIVE_URL` no longer matched at import and the published transcript carried a broken link.
