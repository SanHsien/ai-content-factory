# Offline pipeline

The v0.1 pipeline is a local, deterministic sequence with explicit
evidence boundaries. It is the offline core for the public OSS release, not a
live content service.

## Command contract

The documented command surface targets Python 3.11 and the standard library
only. Run it from the repository root without installing a provider SDK:

```text
python -B src/ai_content_factory/cli.py demo --output output
python -B src/ai_content_factory/cli.py inspect --output output
python -B src/ai_content_factory/cli.py validate --output output
```

The standard staging root is `output`. A successful run is resolved to
`output/<run_id>/`; a caller may also pass a specific run directory to the
read-only inspection and validation commands. The run ID is derived
deterministically from the sanitized topic and local profile. It is not a
timestamp, host identifier, account identifier, or private path.

For a custom synthetic topic:

```text
python -B src/ai_content_factory/cli.py run --topic "synthetic review topic" --output output
```

The documentation deliberately passes `--output output` so the staging root
is unambiguous. The current source-tree `demo` convenience default is tracked
separately as a runtime-alignment review item; no documentation command
silently treats an example directory as the standard staging root.

## Stages and evidence

| Stage | Input | Output | Gate |
| --- | --- | --- | --- |
| 1. Intake/topic | Sanitized topic and optional local profile | `content_packet.json` | Reject empty or unsanitized input; no private identity is required |
| 2. Research fixture | Topic and synthetic local fixture | `research.json` | Mark evidence as fixture-only; do not imply live research |
| 3. Text | Structured research result | `article.md`, `short_script.md` | Preserve deterministic text metadata and bounded claims |
| 4. Storyboard | Text and local descriptors | `storyboard.json` | Describe intended assembly without private assets |
| 5. Media | Prompts and fixture providers | `media_manifest.json` | Return placeholder descriptors, not media bytes or remote URIs |
| 6. Media QA | Media descriptors and package state | `qa_scorecard.json` | Fail unsafe or incomplete local contracts |
| 7. Approval | Validated local packet | `approval.json` | Record state only; approval is not public authorization |
| 8. Publish package | Approved local artifacts | `publish_manifest.json`, `demo_preview.html`, `platform-ready/<platform>.txt`, and `run_log.jsonl` | Accept only `approval_status=APPROVED`, `approval_integrity=PASS`, and `remote_write=0`; handoff remains local |
| 9. Human decision | Evidence packet | Continue, revise, or stop | No external action is implied |

The intended flow is:

```text
sanitized topic → local fixture → draft → package → local QA
                → redacted scan → Stranger Test → human decision
```

There is no remote publish stage in this phase. Browser automation, account
onboarding, credential setup, payment, distribution, and external provider
calls are separate future decisions and must not be inferred from a local
package.

## Output layout

Generated output is ignored by the repository and should remain disposable
staging evidence:

```text
output/
└── <run_id>/
    ├── pipeline_state.json
    ├── run_log.jsonl
    ├── packet_seed.json
    ├── content_packet.json
    ├── research.json
    ├── article.md
    ├── short_script.md
    ├── storyboard.json
    ├── media_manifest.json
    ├── qa_scorecard.json
    ├── approval.json
    ├── publish_manifest.json
    ├── demo_preview.html
    └── platform-ready/
        └── <platform>.txt
```

The state file records stage status, attempts, digests, and structured failure
codes. The run log records structured local lifecycle events. Canonical JSON
and SHA-256 digests make repeated local runs comparable; they do not establish
source truth or external delivery.

## Resume, inspect, and validate

`resume` continues a paused or failed local run and does not create a second
remote action. `inspect` reads persisted state without writing. `validate`
checks required files, JSON shape, platform text consistency, path safety,
zero remote-write state, and forbidden metadata without changing the run.

The validation boundary is intentionally modest: it checks the local package
contract and selected metadata. It does not verify external accounts,
publisher availability, current facts, rights, or the safety of data outside
the selected root.

## Failure handling

Any scanner finding, missing provenance, invalid local artifact, ambiguous
license or rights source, or unclear security boundary pauses package review.
Preserve redacted evidence and record the uncertainty. Do not make output look
clean by deleting a finding, copying a private value into a fixture, or
silently widening scope.

The safe outcomes are:

- `SUCCEEDED`: the local stage graph and package checks completed.
- `PAUSED`: a requested local stop point was reached.
- `FAILED`: a structured local error was persisted.
- `DUPLICATE`: a deterministic run already exists and was not overwritten.
- `HUMAN_REVIEW` or `BLOCKED`: the next boundary needs an explicit decision.

None of these statuses means public publication, account approval, payment,
revenue, or production suitability.
