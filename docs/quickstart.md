# Quickstart

## Requirements

- Python 3.11 or newer.
- Windows 10/11 for the primary instructions.
- About 50 MB of free space for source, a virtual environment, and demo output.

The base demo needs no network, package index, API key, account, GPU, model
weight, browser, Node.js, or FFmpeg.

## Windows PowerShell

Run from the repository or extracted release-candidate directory. The launcher
selects the newest installed Python 3 runtime; the first command enforces the
project minimum without requiring a specifically installed `3.11` executable:

```powershell
py -3 -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer required'; print(sys.version)"
py -3 -m venv .venv
.venv\Scripts\python -B scripts\bootstrap_offline.py
.venv\Scripts\ai-content-factory --help
$result = .venv\Scripts\ai-content-factory demo --output output | ConvertFrom-Json
Invoke-Item $result.visible_artifact
.venv\Scripts\ai-content-factory inspect --output output
.venv\Scripts\ai-content-factory validate --output output
.venv\Scripts\python -B scripts\public_ci.py
```

Expected terminal status is `SUCCEEDED`. The preview path is also printed as
`visible_artifact`. The read-only `inspect` and `validate` commands accept the
`output` parent and resolve its single generated run directory.

## Windows CMD

Run from the repository or extracted release-candidate directory:

```bat
py -3 -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer required'; print(sys.version)"
py -3 -m venv .venv
.venv\Scripts\python.exe -B scripts\bootstrap_offline.py
.venv\Scripts\ai-content-factory.cmd --help
.venv\Scripts\ai-content-factory.cmd demo --output output
.venv\Scripts\ai-content-factory.cmd inspect --output output
.venv\Scripts\ai-content-factory.cmd validate --output output
.venv\Scripts\python.exe -B scripts\public_ci.py
```

Open the `demo_preview.html` path shown in the JSON output. The `inspect` and
`validate` commands accept the `output` parent and resolve its single generated
run directory.

## Linux or macOS

The base path is designed to be portable across POSIX runtimes. The following
is the complete documented Linux/POSIX Stranger path and uses the normal
`python3` command, which may resolve to any supported Python 3.11-or-newer
runtime:

```bash
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer required"; print(sys.version)'
python3 -m venv .venv
.venv/bin/python -B scripts/bootstrap_offline.py
.venv/bin/ai-content-factory --help
.venv/bin/ai-content-factory demo --output output
.venv/bin/ai-content-factory inspect --output output
.venv/bin/ai-content-factory validate --output output
.venv/bin/python -B scripts/public_ci.py
```

The exact path above was executed in a clean Linux runtime for Final3. A real
macOS runtime was not available for this verification, so macOS remains
`MACOS_REAL_RUNTIME_VERIFIED=NO`; this is not a macOS integration pass claim.

## Verify the output

The documented Windows and POSIX flows above already run `inspect`, `validate`,
and `public_ci`. The output directory contains `demo_preview.html`, JSON and
Markdown pipeline artifacts, `publish_manifest.json`, and
`platform-ready/*.txt`. These are local review files. Nothing is uploaded.

## Remove the local setup

Close any process using the virtual environment, then remove `.venv` and
`output`. They contain only local launch files and generated demo artifacts.
The source tree is unchanged.
