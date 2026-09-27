# Stranger Test

The release gate is a clean-copy test performed as if the original developer
were unavailable.

## Procedure

1. Build an allowlist release candidate outside the working repository.
2. Copy or extract it to a new temporary directory without `.git`, `.venv`,
   output, caches, or environment configuration.
3. Follow only `README.md`: create a new virtual environment and run the
   standard-library bootstrap.
4. Run `--help`, public tests, the redacted scan, the demo, and validation.
5. Confirm `demo_preview.html` opens and the platform package exists.
6. Record every undocumented intervention. Any intervention makes the run fail.

## Pass conditions

- no API key, account, private asset, private path, model, or network is used;
- the tests and public scan pass;
- the demo and validation return success;
- the preview is self-contained and visibly meaningful;
- errors and optional capability boundaries are documented; and
- `REMOTE_WRITE=0` throughout.

This verifies the local RC on the tested Python/OS combination. It does not
prove every machine, optional provider, model, or external service.
