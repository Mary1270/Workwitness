# Testing

## Commands

```bash
python3 scripts/check_contracts.py
python3 -m unittest discover -s tests -t tests -v
node --test tests/frontend/lib.test.mjs
python3 scripts/build_release.py
```

No packages are installed for the Python suite. CI (`.github/workflows/ci.yml`) runs lint, the static deploy checks, the offline suite, the build and the frontend tests on every push.

## The offline SDK stub

`tests/genlayer_stub/genlayer/__init__.py` re-implements just enough of the SDK: `gl.Contract`, `public.view/write/write.payable`, `message.sender_address/value`, `get_contract_at(...).view()/emit()/emit_transfer()`, `vm.run_nondet_unsafe`, `nondet.web.render`, `nondet.exec_prompt`, `TreeMap`, `DynArray`, `u256`, `Address`, `UserError`.

It deliberately reproduces failure modes learned on GenLayer Studio, so the same mistakes fail offline:

| Reproduced behavior | Why |
|---|---|
| Assigning `{}` to a `TreeMap` field raises | Real GenVM rejects it; fields are zero-initialised |
| `TreeMap.get()` raises | Avoid unsupported storage calls |
| Web/model calls outside a non-deterministic block raise | Real GenVM forbids them |
| Contract calls and transfers inside a non-deterministic block raise | No cross-contract calls mixed with non-determinism |
| `emit_transfer` to a wallet accepts only `value=` | Real GenVM errors otherwise |
| Failed transactions roll back all state and balances | Atomicity |
| Failed `emit` messages are swallowed and recorded in `RT.failed` | Asynchronous messages cannot revert the sender |
| Each simulated validator can have its own pages and model | Independent fetch/evaluation |

Consensus in the stub: the leader plus 4 validators; accepted when strictly more than half return `true` from `validator_fn`; otherwise a `ConsensusFailure` rolls the transaction back. The real protocol's thresholds may differ.

`scripts/check_contracts.py` additionally enforces what the stub cannot: exactly two header lines and no other comments or docstrings, no storage assignment in `__init__`, no `.get()` on storage, no captured `self` in non-deterministic closures, no floats, no forbidden imports.

## Coverage map

| Area | File | Examples |
|---|---|---|
| WorkLog | `tests/test_worklog.py` | valid/invalid/duplicate claims, URL rules, excessive input, unauthorized modification, state transitions, deposits |
| SkillVerifier | `tests/test_skill_verifier.py` | PASS/FAIL/INSUFFICIENT, unavailable and conflicting sources, duplicate content, validator disagreement, leader tampering, repeated evaluation, timeouts, challenge flow |
| ScoreRegistry | `tests/test_score_registry.py` | score math and bounds, duplicate-work and daily-cap rules, replay protection, history, authorization |
| Message timing | `tests/test_skill_verifier.py::MessageTiming` | score/bond messages are `finalized`, orphan jobs cannot finalize |
| Recovery | `tests/test_recovery.py` | dropped `open_job`, `close_claim` and `record_result` messages and their repair |
| Security | `tests/test_security.py` | one class per threat T01–T11 of `THREAT_MODEL.md`, end to end through all three contracts, plus static checker tests |
| Frontend helpers | `tests/frontend/lib.test.mjs` | escaping, routing, formatting, URL safety |

## Live testing

See `DEPLOYMENT.md`. The live scenarios use real public pages and a real model, so a verdict can legitimately differ from the expected one; the script prints both. A live run is the only evidence that the contracts behave on the real runtime; the offline suite cannot substitute for it.
