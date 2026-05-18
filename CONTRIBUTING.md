# Contributing to DCP

Thanks for caring enough to read this file. DCP is small enough that almost
any well-scoped contribution moves the needle.

## Scope

DCP is a protocol, a reference Python bridge, and reference firmware. We are
deliberately keeping scope tight in v0.x: real devices, real LLMs, real
demos beat speculative architecture.

What we welcome most right now:

- **Additional transport implementations** (CoAP, USB-CDC native, RS-485 multi-drop).
- **Reference firmware ports** to other MCUs: nRF52, STM32, RP2040, ESP32-C3.
- **Bug reports with reproducible cases** — especially anything where the
  Bridge accepts something it should have rejected.
- **Conformance tests**: golden frames, manifest edge cases.
- **Real-device manifests** for things you actually own.

What we politely defer for now:

- Major spec rewrites before v1.0.
- Renames, restructures, and other churn that doesn't move us toward a demo.
- Features that require negotiating new on-device crypto code paths
  (we will get there, but later).

## Development setup

```bash
git clone <repo>
cd <repo>
python -m pip install -e ".[mcp,serial,mqtt,ble,dev]"
pytest
ruff check src tests
```

CI runs both pytest and ruff on Linux + Windows × Python 3.11 – 3.13. PRs
that fail CI will be asked to fix it before review.

## Coding standards

- Python: ruff config is in `pyproject.toml`. No black, no isort — ruff
  does both.
- C++ firmware: keep allocations static, no exceptions, no RTTI.
- No comments that just restate what the code does. A "why" line is fine.
- Public APIs need docstrings; private helpers usually don't.
- Tests live in `tests/`, named `test_*.py`.

## Commit and PR style

- Subject line under 70 chars, present tense (`Add MQTT transport`, not
  `Added`).
- Reference any issue this closes in the PR description, not the commit.
- Squash to one commit per logical change before requesting review.

## Spec changes

If your PR changes the wire format, the manifest schema, or the safety model,
say so explicitly in the PR description and tag the title `spec:`. We will
require a design rationale comparable to what is in `docs/RATIONALE.md`.

## Reporting security issues

Do **not** open public issues for security problems. See `SECURITY.md`.

## License

By contributing, you agree your contributions are licensed under MIT.
