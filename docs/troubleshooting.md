# Troubleshooting

## `py -3.11` is not found

Install Python 3.11 or newer from a trusted distributor and enable the Python
launcher. `python --version` may be used instead when it resolves to 3.11+.

## Bootstrap reports that the package source is missing

Run the command from the extracted project root. The directory must contain
both `scripts/bootstrap_offline.py` and `src/ai_content_factory`.

## The CLI command is not found

Use the launcher inside the environment:
`.venv\Scripts\ai-content-factory.cmd`. Re-run the bootstrap with the same
virtual environment if it is missing.

## Demo reports a duplicate run

The same deterministic topic already exists in that output directory. Use
`--resume`, inspect the existing run, or choose a different empty output
directory. The CLI does not overwrite a completed package.

## Validation reports approval invalidated

An approved artifact changed. Start a new run from clean inputs; do not patch
the old approval record.

## Optional image, voice, or video tool is missing

The base demo remains available. Optional commands require their documented
adapter, model/tool, license, and configuration. There is no automatic private
fallback.

## A path appears in an error

CLI errors are intentionally sanitized. Run `inspect` and `validate`, then use
the structured error code. Do not paste credentials or private paths into a
public report.
