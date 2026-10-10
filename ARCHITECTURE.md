# Architecture

## 1. Components and wiring

| Contract | Storage (summary) | Wired to |
|---|---|---|
| `WorkLog` | `claims` (immutable JSON), `claim_state` (status/verdict), `fingerprints`, per-agent open list and history, `deposits`, `locked_total` | `verifier` (set once by owner) |
| `SkillVerifier` | `jobs` (snapshot, rounds, challenge), `deposits`, `forfeited`, `job_ids`, `window` | `worklog`, `registry` (set once) |
| `ScoreRegistry` | `agents` (score, counters, 20 recent credited works), `records` (per claim), `agent_list`, `recent`, totals | `verifier` (set once) |

Wiring order: deploy all three, then `WorkLog.set_verifier`, `ScoreRegistry.set_verifier`, `SkillVerifier.wire`. Each is owner-only and can happen once. `renounce_ownership` removes the owner entirely.

Cross-contract calls are asynchronous messages. `open_job` uses `emit(on="accepted")`: if an appeal later reverses `request_verification`, the orphan job is harmless (a repeated request re-sends `open_job`, which is rejected as "job already exists" while the first job is reused; an orphan job whose claim is not `VERIFYING` cannot finalize or score), and waiting for finality would delay every verification. `record_result` and `close_claim`, which move scores and bonds, use `emit(on="finalized")`: GenLayer documents that an `accepted` message "was already sent and cannot be recalled" if an appeal changes the parent result, and may be re-emitted across appeal rounds. `scripts/check_contracts.py` rejects any other message sent with `accepted`. No contract performs a non-deterministic operation and a cross-contract call in the same method: `evaluate` is the only non-deterministic method and it calls no other contract. Receiving methods are idempotency-guarded (state checks, `already recorded`).

## 2. Data model

Claim (immutable, `WorkLog.claims[id]`): `id, agent, task, expected_result, sources[{url, domain, key}], tokens[≤128, stopwords removed], fingerprint, submitted_at, bond`.

Claim state (mutable only by the rules below): `status ∈ {SUBMITTED, VERIFYING, FINALIZED, CANCELLED}, verdict, verifying_at, finalized_at`.

Job (`SkillVerifier.jobs[id]`): snapshot of the claim fields, `state`, `begun_at`, `verified_at`, `finalized_at`, `round1/round2 {verdict, items[{i,status,quote}], at}`, `challenge {challenger, reason, at, bond, outcome}`, `final_verdict`, `timed_out`.

Agent record (`ScoreRegistry.agents[addr]`): `score, total, passes, fails, insufficient, credited, day, gain, work[], history[≤100]`. Per-claim `records[id]`: `verdict, delta, reason, score_before, score_after, at` (permanent, so the score is replayable).

## 3. State machines

### WorkLog claim status

```
            submit_claim
   (none) ───────────────▶ SUBMITTED ──cancel_claim (agent)──▶ CANCELLED
                              │
                              │ request_verification (agent only)
                              ▼
                          VERIFYING ──close_claim (SkillVerifier only)──▶ FINALIZED
```

### SkillVerifier job state

```
 open_job (WorkLog only)
        │
        ▼
    VERIFYING ──expire_verification (anyone, ≥ 24 h)──┐
        │ evaluate (agent first hour, then anyone)     │ verdict = INSUFFICIENT_EVIDENCE, timed_out
        ▼                                              ▼
     VERIFIED ◀───────────────────────────────────────┘
        │  │
        │  └─challenge (bonded, once, inside window)──▶ CHALLENGED
        │                                                 │ evaluate (re-evaluation, final)       │ expire_challenge (≥ 24 h)
        │                                                 ▼                                       ▼
        │ finalize (anyone, after window)          CHALLENGE_RESOLVED ◀──────────────────────────┘
        ▼                                                 │ finalize (anyone)
     FINALIZED ◀──────────────────────────────────────────┘
```

Invalid transitions, all rejected and tested: `evaluate` outside VERIFYING/CHALLENGED; `challenge` outside VERIFIED, after the window, or a second time; `finalize` before the window, while CHALLENGED, or twice; `expire_*` before their timeouts or in the wrong state; `open_job` twice or from anyone but WorkLog; `close_claim`/`record_result` from anyone but the wired contracts or twice for one claim.

Failure and disagreement handling: if validators do not agree, the transaction fails and nothing changes (state remains retryable). A claim cannot be stuck because anyone can expire a stalled verification (→ INSUFFICIENT_EVIDENCE) or stalled challenge (→ original verdict, bond refunded) after 24 hours.

## 4. Verdict derivation (exact rule)

Per source (after fetching and de-duplicating identical content): `supports`, `contradicts`, `irrelevant`, `unavailable`, `duplicate`.

```
S = #supports, C = #contradicts, U = #unavailable, B = #supports whose page text contains the binding code
PASS   if S ≥ 2 and C = 0 and B ≥ 1   (B = #supporting sources that contain the binding code)
FAIL   if C ≥ 1 and S = 0 and (U = 0 or C ≥ 2)
else   INSUFFICIENT_EVIDENCE
```

The binding code is `WW-` plus the first 16 hex characters (upper case) of SHA-256 of `agent|task|expected_result` (lower-cased, whitespace collapsed). Every item carries a boolean `bound`, recomputed by each validator from its own fetch; a leader item whose `bound` flag the validator cannot reproduce is a disagreement. Without a bound supporting page two supporting sources still give only `INSUFFICIENT_EVIDENCE`.

Page text is capped at 16 000 characters. Runs of `<<<`/`>>>` in the page and in the claim text are collapsed before prompting, so neither can forge the page delimiters. A `supports`/`contradicts` needs a 15–200 character quote that is an exact substring of the fetched text. Sources are guaranteed to be from distinct registrable domains by `WorkLog`, so `S ≥ 2` means two independent domains. A model/runtime error for a source is `unavailable`, which can never create a FAIL on its own.

## 5. Consensus rule

* Leader: runs `evaluate_sources` and proposes `{verdict, items}`.
* Validator: fetches every source itself, independently re-derives the verdict and returns `true` iff (a) the leader's items are well-formed and imply the leader's verdict, (b) its own verdict equals the leader's, and (c) every leader quote for a `supports`/`contradicts` item is an exact substring of that source's text in the validator's own fetch (15–200 characters) and shares ≥ 2 content words with the claim. A malformed leader result, an unknown verdict, or any exception is a disagreement.
* Protocol: GenLayer accepts when enough validators return `true`. On failure the whole transaction reverts; GenLayer may rotate the leader.
* The verdict and the quotes are validator-checked. No page hash is stored (a leader-reported hash is unverifiable because honest page bytes differ between fetches). Which of several non-decisive statuses (`irrelevant`, `unavailable`, `duplicate`) a source received is not individually reproduced, only its effect on the verdict.

The leader therefore cannot dictate a consequential verdict: a verdict that honest validators do not reproduce from their own fetches is rejected.

## 6. Score computation and duplicate-credit logic

On `finalize`, `SkillVerifier` emits `ScoreRegistry.record_result(claim_id, agent, verdict, tokens, keys)`. The registry checks the caller, rejects a repeated `claim_id`, then:

```
PASS:    similar(a, b) = |a ∩ b| ≥ 80% · min(|a|, |b|)   (sets of < 3 words must be identical)
         duplicate = any(similar(tokens, w.tokens)) for credited works in the last 7 days
                     or |keys − keys already credited in 7 days| < 2
         if duplicate → delta 0, reason DUPLICATE_WORK
         base = 2 if similar to any of the last 20 credited works, or its sorted content-word
                fingerprint is among the last 400 credited (REPEAT_WORK), else 10
         delta = min(base, 30 − gain_today); 0 → reason DAILY_CAP
FAIL: −30    INSUFFICIENT_EVIDENCE: −2
score = clamp(score + delta, 0, 1000)
```

Failures are never discounted as duplicates.

## 7. Economic model

GEN is used only as bonds, handled with pull payments:

* **Deposit pattern.** Value is attached only to `deposit()`, which cannot revert on valid input. Claims and challenges then debit a stored balance. This avoids the GenVM behavior where value sent to a reverted payable call stays in the contract unrecorded.
* **Claim bond** 0.01 GEN, locked at submission, returned to the agent's deposit when the claim finalizes (any verdict) or is cancelled while `SUBMITTED`. It is a spam cost, not a reward.
* **Challenge bond** 0.05 GEN, debited on challenge. Upheld or expired → returned; rejected → added to `forfeited`, which has no withdrawal path.
* `withdraw()` zeroes the caller's balance before transferring and pays only the caller.
* Invariant (tested): contract balance = Σ deposits + locked bonds (+ forfeited for the verifier).
* There are no validator or challenger rewards; validator economics belong to the GenLayer protocol.

## 8. Access control matrix

| Method | Class | Check |
|---|---|---|
| `WorkLog.deposit/withdraw/submit_claim` | permissionless (caller's own funds/claims) | sender is the agent identity |
| `WorkLog.cancel_claim`, `request_verification` | agent-only | sender == claim agent, status SUBMITTED |
| `WorkLog.close_claim` | verifier-only | sender == wired verifier |
| `WorkLog.set_verifier`, `ScoreRegistry.set_verifier`, `SkillVerifier.wire`, `renounce_ownership` | administrator-only, one-time wiring | owner, only once; no reputation powers |
| `SkillVerifier.open_job` | WorkLog-only | sender == wired WorkLog |
| `SkillVerifier.evaluate` | agent (or challenger for re-evaluation) for 1 h, then permissionless | state and timing guards |
| `SkillVerifier.finalize/expire_*` | permissionless | state and timing guards; `finalize` also needs WorkLog to show `VERIFYING` |
| `SkillVerifier.resend_finalization` | permissionless | job FINALIZED, ≥ 1 h after finalization, at most 3 times |
| `WorkLog.retry_open_job` | agent-only | status VERIFYING, ≥ 1 h after the request |
| `SkillVerifier.challenge/deposit/withdraw` | permissionless (bonded) | deposit, window, once |
| `ScoreRegistry.record_result` | verifier-only | sender == wired verifier, once per claim |
| all `get_*`, `list_*` | public views | bounded page sizes |

## 9. Frontend

Hash-routed single page (`#/`, `#/agents`, `#/agent/<addr>`, `#/claims`, `#/claim/<id>`, `#/submit`). Two visually distinct blocks, **Agent claimed** (amber) and **Validators independently verified** (green), plus a **Final score** block labelled as contract-computed. All dynamic text is HTML-escaped; links are rendered only for `https` URLs. No statistic or score is hard-coded; every number is read from the contracts.
