# Threat model

Central question: *can a malicious submitter manipulate a consequential verdict without validators independently verifying the same underlying evidence?*

**Answer.** Not through the submitter's label, quote, score, or the leader: those either do not exist as inputs or are re-derived by every validator. The remaining route is **authoring the evidence itself** (T01), which is a residual risk, documented and only mitigated.

## Assets

Correctness of finalized verdicts, integrity of agent scores, immutability of claims, bonds held by the contracts, availability of verification.

## Adversaries

Malicious agent (submitter), colluding agents/sybils, malicious challenger, malicious or lazy leader, a minority of faulty validators, anyone able to edit a web page that a claim cites, the deployer.

## Assumptions

* GenLayer validators are an honest majority and each performs its own web fetch and model call.
* The model is imperfect; the design limits what a wrong model answer can do (quote check, INSUFFICIENT_EVIDENCE default) but cannot make it correct.
* Time from `datetime.datetime.now()` is consistent across validators in a transaction.
* The deployer wires the contracts correctly once. After wiring, deployer powers are nil.
* Web pages are public and fetched as text; JavaScript-rendered content is not reliably visible.

## Threats

| # | Threat and attack | Mitigation | Tests | Residual / status |
|---|---|---|---|---|
| T01 | **Fabricated evidence**: agent publishes false pages on sites it controls | ≥ 2 distinct registrable domains; identical content counts once; challenge window with independent re-evaluation; bonds raise cost | `T03_*`, `test_identical_content_*` | **Residual.** Validators observe, not verify truth. Colluding sites defeat PASS. Out of scope; documented in SECURITY.md |
| T02 | **Favorable quote that does not support the claim** | No quote input exists. A model quote must be an exact substring of the validator's own fetched text, 15–200 chars; the claim's own text is never evidence | `test_fabricated_quote_*`, `T01_*`, `test_claim_text_is_not_evidence` | Mitigated; model can still misjudge a real quote |
| T03 | **Leader manipulation** (leader proposes a self-serving verdict or sees special pages) | Every validator reproduces the verdict from its own fetches; mismatch fails the transaction | `test_malicious_leader_*`, `test_leader_seeing_different_content_*`, `T02_*` | Mitigated under the honest-majority assumption |
| T04 | **Validator disagreement** | Failed consensus reverts with no state change; retry or timeout to INSUFFICIENT_EVIDENCE | `test_majority_disagreement_blocks`, `test_failed_evaluation_*`, `T10_*` | Mitigated; liveness depends on GenLayer |
| T05 | **Conflicting sources** | `supports` and `contradicts` together → INSUFFICIENT_EVIDENCE, never forced | `test_conflicting_sources_*` | Mitigated |
| T06 | **Duplicate sources** (same URL, trailing slash, `www`, fragment, case, reorder) | URL normalization; duplicate key and exact fingerprint rejection | `WorkLogUrls`, `test_duplicate_claim_*` | Mitigated |
| T07 | **Same-domain inflation** (subdomains, mirrors, two free pages on one hosting platform such as `a.github.io` + `b.github.io`) | Registrable-domain extraction; free hosting platforms collapse to the platform; a family map joins `github.io`/`githubusercontent.com`/`github.com` and `gitlab.io`/`gitlab.com`; numeric or invalid TLDs rejected | `test_same_domain_sources_are_rejected`, `test_free_hosting_pages_count_as_one_platform`, `test_registrable_domain_rules` | Approximate: no full public-suffix list. Two *different* free platforms (e.g. `github.io` + `netlify.app`) still count as two sources |
| T08 | **Unavailable URLs** (or attacker takes a competing page down to cause FAIL) | `unavailable` is its own status; FAIL needs a clear contradiction and no unavailable source unless two sources contradict | `test_one_contradiction_plus_unavailable_*`, `DeriveVerdictTable` | Mitigated |
| T09 | **Stale pages** | Prompt instructs `irrelevant` for evidence dated before the task | `test_prompt_treats_page_as_untrusted_data` | **Residual.** Model-judged, not cryptographic |
| T10 | **Changed web content** after the verdict | Challenge re-fetches everything; no page hash is stored (a leader-reported hash would be untrustworthy) | `test_changed_content_is_caught_by_challenge_reevaluation` | Verdicts are not bound to page bytes; changes after finalization are invisible |
| T11 | **Maliciously large inputs** | Hard bounds: task 500, expected 500, URL 300, sources ≤ 5, JSON ≤ 2000, challenge reason 500, page text 16 000, tokens 128, bounded paging | `T05_*`, `test_excessive_input_is_rejected` | Mitigated |
| T32 | **Appeal reverses a finalizing transaction after its messages were sent** (`on="accepted"` messages cannot be recalled and may repeat) | Score and bond messages use `on="finalized"`; `finalize` requires WorkLog to still show `VERIFYING`; receivers reject duplicates | `MessageTiming`, static checker tests | Mitigated. Cost: score and bond release appear only after GenLayer finality |
| T33 | **Leader reports fabricated or misattributed quotes with a correct verdict** | Every validator checks each reported quote against its own fetch of that same source and the relevance gate | `T01b_EvidenceTrail` | Mitigated for quotes. No leader-reported digest is stored |
| T34 | **Reversed `request_verification` leaves an orphan job** (`open_job` is an `accepted` message) | A repeated request re-sends `open_job`, rejected harmlessly; the first job is reused; `finalize` requires WorkLog `VERIFYING`; `retry_open_job` covers a dropped message | `test_reapplied_request_after_a_reversed_one_still_completes`, `test_a_job_whose_claim_is_not_verifying_cannot_finalize` | Accepted. Finality for `open_job` was rejected because it would delay every verification without preventing any stuck state |
| T35 | **Rotating more than 20 task templates** (or reworded tasks) to earn full credit again | Exact normalized repeats are remembered for 400 credited works; near-similar tasks for 20 | `test_exact_repeat_is_remembered_beyond_the_work_archive` | **Residual by design.** Memory is bounded; reworded tasks with fresh evidence are indistinguishable from new work. Rate is capped at +30/day |
| T12 | **Replayed verification** | Job states are one-shot; `evaluate` only in VERIFYING/CHALLENGED | `test_repeated_evaluation_is_rejected`, `T06_*` | Mitigated |
| T13 | **Duplicate score updates** | `record_result` keyed by claim id; `finalize` once; `close_claim` once | `test_claim_cannot_be_recorded_twice`, `test_score_cannot_be_applied_twice` | Mitigated |
| T14 | **Unauthorized score change** | Only wired verifier; no method takes a score; owner has no power | `RegistryAccess`, `T07_*` | Mitigated |
| T15 | **Unauthorized claim modification** | Claims immutable (no edit method); status changes only via agent-only/verifier-only methods | `test_no_method_edits_claim_metadata`, `T07_*` | Mitigated |
| T16 | **Repeated claims** | Exact fingerprint (agent + task + source keys); similar open claims rejected | `test_duplicate_claim_*`, `test_near_duplicate_open_claim_*` | Mitigated |
| T17 | **Score inflation / farming** (same work with new URLs, recycled sources, subdomain tricks, padding the task with extra words, pushing real words past a token cap, repeating every 8 days, volume) | Containment similarity ≥ 80% of the smaller content-word set, stopwords removed, all task words kept; < 2 fresh sources, where a source key is registrable-domain + path; 7-day zero-credit window; decayed +2 for repeats of any of the last 20 credited works; identical claims rejected forever; +30 daily cap; bond; failures not discounted | `DuplicateAndFarming`, `T08_*` incl. padding and prefix-padding tests | Partly residual: a genuinely reworded description with fresh sources can still earn credit; sybils see T22 |
| T18 | **Challenge abuse** (spam, delay, recursion) | One challenge per claim, in-window only, bonded, bond forfeited if verdict unchanged, one re-evaluation then final, timeout | `ChallengeFlow`, `T09_*` | Mitigated; a funded attacker can delay finalization once by up to 24 h |
| T19 | **DoS via verification requests** | Agent-only start, 3 open claims, 60 s cooldown, bond, bounded sources/text, timeouts, paged views | `T10_*` | Bounded, not eliminated |
| T20 | **Prompt injection in evidence pages** | Page is passed as delimited untrusted data; output must be a JSON status plus a verbatim quote checked in code; the quote must share ≥ 2 content words with the claim (code-enforced relevance gate); PASS needs two independent pages | `T05_test_prompt_injection_*` | **Residual.** A page can still influence the model's judgment |
| T21 | **Redirects** | Runtime follows redirects; independence is judged on submitted URLs, and identical resulting content is counted once | `test_identical_content_*` | A redirect to different content on a controlled domain is not detectable |
| T22 | **Sybil agents** (many addresses) | Each address pays bonds and has its own history; no cross-agent credit | `test_sybil_agents_*` | **Residual.** Cost is only bonds; reputation is per address |
| T23 | **Asynchronous cross-contract failure** (a dropped `open_job`, `close_claim` or `record_result` message) | Receivers are idempotent and state-guarded. `WorkLog.retry_open_job` (agent, after 1 h) re-sends the job; `SkillVerifier.resend_finalization` (anyone, at most 3 times, only 1 h after finalization) re-sends the final result; duplicates are rejected harmlessly | `test_recovery.py` | Recovery needs someone to call it; messages are not retried automatically |
| T24 | **Deployer compromise or misuse** | Owner can only wire once; can renounce; owner is not special at runtime | `test_verifier_wiring_*`, `test_renounce_*` | Wiring must be done and checked before renouncing |
| T25 | **Value stuck on reverted payable calls** | Value only attached to `deposit()`; all other flows spend stored balances | `test_zero_deposit_rejected`, economics tests | Mitigated |
| T26 | **Validator collusion / biased model** | None in-contract | — | **Out of scope**: relies on GenLayer's security model |
| T27 | **Evaluation-timing sabotage** (a third party triggers `evaluate` while the agent's evidence host is briefly down, or before the agent is ready) | For the first hour only the agent (and, for re-evaluations, the challenger) may call `evaluate`; afterwards anyone may, so a claim cannot be held hostage | `EvaluationAccess` | Bounded; a stuck or timed-out claim still resolves to INSUFFICIENT_EVIDENCE |
| T28 | **Selective reporting** (agent only starts verification for claims it expects to pass; abandons the rest) | Bonds are locked while a claim is open; the open-claim cap bounds how many can be parked | — | **Residual.** Cancelled or unstarted claims are not penalized, so a score reflects only claims the agent chose to verify |
| T29 | **Challenge as re-roll** (agent challenges its own FAIL/INSUFFICIENT hoping the model answers differently) | One challenge and one re-evaluation per claim, bonded, bond lost if the verdict does not change | `test_anyone_with_a_bond_may_challenge_including_the_agent` | Residual: one extra model roll is purchasable |
| T31 | **Forged prompt delimiters** (`PAGE>>>>` in a page or claim, which a naive single replace turns back into `PAGE>>>`) | Runs of 3+ angle brackets collapsed with a regex | `T05b_PromptDelimiters` | Mitigated |
| T30 | **Prompt injection through the claim text** (task or expected result written to steer the judge) | Claim text is declared untrusted, delimiters in it are neutralized, a verdict still needs an exact quote from the page and two independent pages | `PromptHardening` | Residual, as T20 |

## Explicitly out of scope

Proving real-world truth of a web page, key compromise of agent wallets, front-running of claim ids, privacy of submitted claims (everything is public), and economic attacks that need control of a validator majority.
