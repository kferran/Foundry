---
type: schema
schema_for: meeting_transcript
folders: ["wiki/work/meetings/", "wiki/personal/meetings/"]
fields:
  type: {kind: const, value: meeting_transcript, required: true}
  meeting: {kind: link, required: true}
  partition: {kind: enum, values: [work, personal], required: true, matches_folder: true}
  source: {kind: string, required: true}
  complete: {kind: bool}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Meeting transcript
The redacted transcript beside its meeting note, named `<meeting note>.transcript.md`: one `**Speaker:** text` turn per line under `### HH:MM:SS` headings. `complete: false` means the Doc's text ended before its end marker.
