---
type: schema
schema_for: meeting_transcript
folders: ["wiki/work/meetings/", "wiki/personal/meetings/"]
fields:
  type: {kind: const, value: meeting_transcript, required: true, readers: [system/scripts/vaultlib/schema.py]}
  meeting: {kind: link, required: true, readers: []}
  partition: {kind: enum, values: [work, personal], required: true, matches_folder: true, readers: []}
  source: {kind: string, required: true, readers: [system/scripts/vaultlib/intake.py]}
  complete: {kind: bool, readers: []}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}, readers: [system/scripts/vaultlib/publish.py]}
---
# Meeting transcript
The redacted transcript beside its meeting note, named `<meeting note>.transcript.md` (a later drop for a note with content gets its own free name, and `meeting` links the note it joins): one `**Speaker:** text` turn per line under `### HH:MM:SS` headings. `complete: false` means the Doc's text ended before its end marker.
