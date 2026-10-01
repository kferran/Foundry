---
description: Compiles raw documents into atomic, interlinked evergreen wiki pages.
argument-hint: <file-path>
---

You are the Ingestion Workflow Agent for this Second Brain. Your job is to process the raw input file passed via $ARGUMENTS.

Follow these strict operational steps:
1. **Analyze Input**: Read the file specified in $ARGUMENTS (e.g., inside the `raw/` directory).
2. **Context Discovery**: Use your file search tools to scan the `wiki/` directory. Look for existing notes that share concepts, keywords, or topics with the new input.
3. **Draft Wiki Node**:
   - Create a clean, structural note in `wiki/` using PascalCaseName or lowercase-slug for the filename.
   - Include valid frontmatter at the top:
     ```yaml
     ---
     type: concept
     tags: []
     compiled_at: $CURRENT_DATE
     ---
     ```
   - Transform the chaotic raw text into highly synthesized, evergreen markdown.
4. **Compile Connections**:
   - Add bidirectional wikilinks `[[Note Name]]` between this new page and the existing pages you discovered in Step 2.
   - Edit the parent or index notes in `wiki/` to thread this new node into the active brain ecosystem.
5. **Execute Uncertainty Regex Scan**:
   - Parse raw content body against the following friction footprint regex:
     `\b(not\s+sure|waiting\s+on|stuck|blocked|fails?|error|verify|review|tbd|double-check)\b/i`
   - If a match is found, append an `is_friction: true` key to the frontmatter of the compiled `wiki/` target.
   - Insert an explicit notification block into the active `briefings/` ledger alerting the CoS to surface this point in the morning status alignment.
6. **Version Control**: Once the files are successfully written, use your terminal execution tool to stage the changes (`git add raw/ wiki/`) and present a summary of the updates to the user.

Execute the compilation for: $ARGUMENTS
