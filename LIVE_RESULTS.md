# Live results (GenLayer Studio, 2026-10-08)

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
- Not exercised live: resend_finalization and retry_open_job (nothing stalled).
- Not measured: protocol finality on a production network. Studio finalizes in minutes.
