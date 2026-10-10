# Live results (GenLayer Studio, 2026-10-08)

> These results are for v1.0.0 (before evidence binding). v1.1.0 adds the binding code (a PASS requires the agent-specific code on a supporting page); its live results are listed at the end of this file once collected.

Test build, challenge window 300 s. All three contracts deployed and wired by one deployer wallet.

| Contract | Address |
|---|---|
| ScoreRegistry | `0x227D611422D6fBE5722e1fB9D3b3BFbc16179aF1` |
| WorkLog | `0x539929f944dA65c0edB304f3cB75A39cbF5346A2` |
| SkillVerifier | `0x6603CAed9d9F5e1Ba54d003A592FDC5203138500` |

## Measured chain

| Step | Result |
|---|---|
| deploy x3, set_verifier x2, wire | SUCCESS |
| request_verification -> open_job (accepted child message) | job created about 55-77 s after submit_claim |
| evaluate (full consensus, web fetch + LLM) | about 1-2 min, SUCCESS |
| finalize -> record_result + close_claim (finalized child messages) | effects visible within about 2 min |
| bond refunds (claim bond) | returned in full on every claim |
| challenge (bonded, in window) -> re-evaluation | REJECTED, challenger bond forfeited |
| withdraw to an EOA (WorkLog and SkillVerifier) | SUCCESS, exact amounts |

## Verdicts

| Claim | Verdict | Score delta |
|---|---|---|
| 1 (python.org + endoflife.date) | INSUFFICIENT_EVIDENCE | -2 |
| 2 (python.org + devcenter.heroku.com), challenged | PASS | +10 |
| 3 (task contradicted only by inference) | INSUFFICIENT_EVIDENCE | -2 |
| 4 (explicit contradiction on python.org) | FAIL | -30 |

Final score 476 (500, -2, +10, -2, -30).

## Findings

- Claim 1: the evidence row on endoflife.date sits about 25,000 characters into the page, past the 16,000 character cap, so only one source supported the claim. Pick sources whose evidence is near the top of the page.
- Claim 3: a page that only implies the opposite is judged irrelevant, so FAIL needs an explicit contradiction. This is intended.
- The Studio Value field is in GEN, not wei. Entering wei multiplied the deposits by 1e18; contract logic was unaffected.
- One evaluate (claim 5) ended UNDETERMINED after three leader rotations, with two of four validators disagreeing. Contract state was unchanged, the claim stayed VERIFYING, and calling evaluate again was accepted on the first round with PASS. Cause not isolated (live page or model variance).
- The frontend (GitHub Pages, `docs/`) completed a full cycle with a second wallet: deposit, submit, request verification, evaluate, challenge (bond deposited by the UI), re-evaluation, finalize, withdraw. A repeat PASS for the same sources earned +0 (verified, no credit), as designed.
- Not exercised live: resend_finalization and retry_open_job (nothing stalled).
- Not measured: protocol finality on a production network. Studio finalizes in minutes.

## v1.1.0 (evidence binding), live on GenLayer Studio, 2026-10-10

Test build, challenge window 300 s. Deployer and agent wallet `0xf73699c4A8C35a10fBFa74ca07CbEcA99b148Ffd`.

| Contract | Address |
|---|---|
| ScoreRegistry | `0xAced46f49Be7b93f71C3cd31301B1A11938311d8` |
| WorkLog | `0x07056A665EED448BCA3AE326F76045Aa0570f6ca` |
| SkillVerifier | `0x9b9d9Ff661f0714bdcFE218e3cfFb991c9f59048` |

| Claim | Sources | Result |
|---|---|---|
| 1 (no binding code anywhere) | python.org + devcenter.heroku.com, both `supports` | `INSUFFICIENT_EVIDENCE`, `bound: false` on both sources |
| 2 (binding code `WW-26A3C9D635EEA7D3` on a GitHub raw file) | raw.githubusercontent.com proof file + python.org, both `supports` | `PASS`, `bound: true` on the proof file, `bound: false` on python.org |

The binding code is a hash of the agent address, the task and the expected result; the code used in claim 2 was also recomputed independently offline and matched `get_binding_code`.

After the challenge window, `finalize(2)` was called and its effects were read back: `SkillVerifier.get_job` state `FINALIZED` with final verdict `PASS`; `ScoreRegistry.get_agent` score 510 (passes 1, credited 1, history `["2"]`) for the claim submitter only; `WorkLog.get_claim` status `FINALIZED`, verdict `PASS`, claim bond returned.
