# KnowHow Tool · V1.5

KnowHow Tool is a local knowledge assistant for Windows by **mRbRaIn0**. Keep
notes, images, and documents in your own knowledge folder, then ask questions
about them with source references. AI runs through Ollama on your computer.
Notes remain ordinary Markdown files that you can also edit in Obsidian.

[Windows release](https://github.com/mRbRaIn0/KnowHow-Tool-Local/releases/latest)
· [Deutsche README](README.de.md) · [AI behavior (German)](KI.md)
· [V1.5 release report (German)](docs/RELEASE-V1.5.md)

## What's new in V1.5

- **Search scope:** Choose a Vault folder beside the model selector. All folders
  are selected by default; subfolders are included. A narrower scope reduces
  search work and irrelevant context.
- **No matching entry:** When a knowledge question has no local match, the UI
  shows the notice once and removes a duplicate if the model writes one.
- **Variants toggle:** Turn on three answer variants when you need them. It is
  off by default for simple questions.
- **Chat context menu:** Right-click a chat to move it to a folder, archive it,
  or delete it. Deletion requires confirmation.
- **Markdown cheat sheet:** View syntax in the Notes sidebar, copy a block, or
  insert it into quick capture at the cursor position.
- **German and English:** Choose the interface language at the bottom of
  Settings. It also controls the AI response language.
- Missing model details are hidden instead of being displayed as `null`.

Included note templates and existing Vault content keep their own language.
Direct file commands and some free-form action recognition still use German;
the prepared actions in the interface work in both languages.

## Earlier updates

### V1.4

- Faster knowledge answers use relevant excerpts and link to source `.md` files.
  Answers without a local match are identified as general AI knowledge.
- The working chat avoids repeated identical search and read calls.
- Larger note tasks can offer Strict, Structured, and Expanded variants. Choose
  one, then accept or request changes. Only acceptance writes to the Vault,
  and the action can be undone.
- Capture notes (Ctrl+Enter), paste or drop images, and drop files onto a folder.
  Duplicate names are numbered. AI actions open a prepared working chat;
  you decide when to send it.
- Notes can use bullet points for facts, tables for comparisons, numbered steps
  for procedures, definitions for terms, and suitable internal links.
- Save answers as numbered notes. Uploads go straight to the Vault while a
  chat copy remains available for analysis.

### V1.3

- Explicit storage commands can copy attachments without a model call or
  content analysis. Duplicate file and note names are numbered automatically.
- Named files and folders restrict search and reading. An explicit whole-Vault
  request can widen the scope.
- A write preview shows the note, diff, source links, and destination before
  saving. The last Vault task can be undone unless newer external changes
  conflict.
- Image OCR and descriptions can be stored as searchable source notes under
  `91 Quellenwissen`. An optional separate vision model can be enabled.

## Two ways to work with your knowledge

| Area | Purpose |
|---|---|
| **Wissen erweitern** (Expand knowledge) | Add information, attach files, analyze images, and create or extend notes. Original files can be stored and linked in the Vault. |
| **Wissen fragen** (Ask knowledge) | Ask questions about saved knowledge. Relevant excerpts and source files are supplied to the model. This area has no writing tools. |

The app also includes a file and note browser with a Markdown editor and
preview, Obsidian WikiLinks, screenshot and image import, PDF/DOCX/text/code
extraction, scanned-page analysis with a local vision model, hybrid SQLite
full-text and Ollama embedding search, separate profiles, chat history,
templates, local ZIP backups, light and dark themes, and a WebView2 window.

**Direct file action:** Append text without a model call by writing
`Füge diesen Text zu SPS/delete2.md hinzu:` followed by the text, even when
the note is empty. Exact paths take priority; multiple matches trigger a
folder question. This command currently requires German wording.
[Commands and limitations (German)](docs/DIRECT-ACTIONS.md).

## Quick start on Windows

1. **Set up Ollama.** Install [Ollama for Windows](https://ollama.com/download/windows)
   and download at least a chat model and the search model. As documented on
   September 11, 2026:

   | Model | Role |
   |---|---|
   | **`qwen3.5:9b`** (default) | General-purpose model for German, reasoning, tools, images, and scanned pages. Requires roughly 8 GB of GPU or system memory. Thinking gives more thorough but slower answers. |
   | **`qwen3.5:4b`** | Smaller and faster, with weaker performance on long notes, difficult scans, and complex tool tasks. |
   | **`qwen3-vl:8b`** | Especially useful for photos, screenshots, and scanned PDFs. It is not a full replacement for the 9B model. |
   | **`nomic-embed-text`** (search) | Local semantic search only, not chat. Keyword search and the file browser still work without it. |

   ```powershell
   ollama pull qwen3.5:9b
   ollama pull nomic-embed-text
   ```

   Optional models for limited memory or more image work:

   ```powershell
   ollama pull qwen3.5:4b
   ollama pull qwen3-vl:8b
   ```

   New profiles start with Thinking off for faster answers. You can enable it
   beside the input. Setup needs internet; normal use can be offline.

2. **Extract the release.** Download `KnowHow-Tool-v1.5-Windows.zip` from
   [Releases](https://github.com/mRbRaIn0/KnowHow-Tool-Local/releases/latest)
   into a writable local folder, such as `%LOCALAPPDATA%/KnowHow-Tool`.
   Chat data lives in `data` **beside** the EXE. Keep that folder when updating.
3. **Launch the app.** Open `KnowHow Tool.exe`. The EXE does not need Python.
   Ollama and its models are separate requirements.
4. **Choose a profile and Vault.** In Settings, select a local folder or an
   existing Obsidian Vault. You can create a separate work profile.
5. **Add and ask.** Start in **Wissen erweitern**, then ask a question in
   **Wissen fragen**.

Image and scan findings must be saved as text notes before they become
searchable knowledge.

## Requirements and limitations

- Windows 10/11, Ollama, and enough memory for the selected model. Speed depends
  especially on the model, GPU, and context size.
- WebView2 for the embedded window. If unavailable, the app attempts a local
  browser in app mode.
- The EXE is unsigned. Managed devices must follow their IT policies.
- Up to 50 attachments per message, 40 MB per file, and 400 MB per chat.
- Missing embeddings do not stop keyword search. Image analysis needs a model
  with vision support.
- AI answers can be wrong. Check important details against original sources.

## Local data and updates

A portable EXE creates `data/` beside itself for configuration, per-profile
databases, uploads, and local logs. A build in this project's `dist/` folder
uses the project's existing `data/`. Your Vault holds notes and original files
separately. The app creates `00 Inhalt.md` as an orientation page while
preserving your rules. Obsidian is optional.

Use **Settings → Data → Backup** for a local copy of the Vault, profile
configuration, and database. The app does not automatically sync devices.

To update without losing chats:

1. Close the running app completely.
2. Download the new release ZIP.
3. Extract it **into the same folder** as the existing `KnowHow Tool.exe`,
   replacing files while keeping `data/`.
4. Start the EXE again. The chat history and Vault path should still be there.

If you extracted into a new folder and the history appears empty, copy the old
`data/` folder beside the new EXE and restart. Extract the ZIP before running
the app; do not launch it from Windows ZIP Explorer.

## Privacy

- The backend listens only on `127.0.0.1`, using a changing port and session key.
- Host and origin checks and a restrictive Content Security Policy are enabled.
- Offline mode is on by default; Ollama connections remain local.
- No telemetry, analytics, or externally loaded CDN resources.
- Models are downloaded only after you explicitly start setup.
- Vault tools check paths and have no shell access.

Release packages and source code do not contain personal profiles, chats,
uploads, Vaults, or models.

## Run from source

Development requires Python; V1.3 was checked with Python 3.12. `start.bat`
creates a local `.venv` with pinned dependencies and starts the app. After
setup, you can also run:

```powershell
.\.venv\Scripts\python.exe run.py
```

Configuration is created on first launch. `config.example.json` documents the
settings. [KI.md](KI.md) describes tools, chat modes, sources, and write
controls in German.

## Check and build the EXE

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q backend run.py
powershell -ExecutionPolicy Bypass -File .\build-exe.ps1
```

The build creates `dist/KnowHow Tool.exe`, the release ZIP, and
`dist/SHA256SUMS.txt`. It bundles license notices from the installed
environment. For reproducible builds, start with a clean environment using
`requirements.txt` and `requirements-build.txt`.

V1.5 passed 241 automated Python tests. Additional build and launch checks
are in the [release report](docs/RELEASE-V1.5.md).

## License

Copyright © 2026 mRbRaIn0. See [LICENSE](LICENSE). Third-party components
retain their own licenses; see [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
