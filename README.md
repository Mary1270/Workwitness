# WorkWitness

Independent, evidence-based reputation for AI agents, built as three GenLayer Intelligent Contracts.

> **Can an AI agent prove that it successfully performed a claimed task?**

An agent submits a *claim*: a task description, the result it expects, and 2–5 public evidence links. GenLayer validators then **fetch the evidence themselves**, evaluate it, and reach one of exactly three verdicts:

| Verdict | Meaning |
|---|---|
| `PASS` | At least two independent sources were observed by the validators explicitly supporting the claimed result, and none contradicted it. |
| `FAIL` | At least one independent source was observed explicitly contradicting the claimed result (with an exact quote), nothing supported it, and no source was unavailable unless two sources contradicted it. |
| `INSUFFICIENT_EVIDENCE` | Everything else: sources unavailable, irrelevant, ambiguous, duplicated or in conflict. Validators are never forced to choose PASS or FAIL. |

The reputation score is derived by the contract from finalized verdicts. Nobody, including the contract owner, can submit or edit a score.

## What WorkWitness does and does not prove

WorkWitness verifies that **independent validators observed public evidence that supports or contradicts a claim**. It does **not** prove that arbitrary public web content is objectively true. An agent that controls two public websites can publish false statements on both. The protocol raises the cost of that (distinct registrable domains, duplicate-content detection, a challenge window, bonds) but cannot eliminate it. It must not be described as a truth oracle. See [SECURITY.md](SECURITY.md).

## Why it exists

Agent reputation today is mostly self-reported or stored by whoever runs the platform. The submitter's label, quote or score must never decide an outcome. In WorkWitness the submitter supplies only links; there is no field for a verdict, quote or score.

## Architecture

```
Agent ──submit_claim──▶ WorkLog ──request_verification (agent only)──▶ SkillVerifier
                          ▲  (immutable claim,                          │ evaluate(): every validator fetches
                          │   status, bond)                             │ every source and re-derives the verdict
                          │                                             ▼
                     close_claim ◀────────────── finalize ──────▶ ScoreRegistry
                     (verifier only)         (after challenge window)   (verifier only, once per claim)
```

| Contract | Responsibility | Never does |
|---|---|---|
| `WorkLog` | Validates and stores immutable claims, source normalization, duplicate/similarity checks, claim bonds, claim status | Judge evidence, touch scores |
| `SkillVerifier` | Validator-consensus evaluation, challenge state machine, challenge bonds, finalization | Store scores, edit claims |
| `ScoreRegistry` | Deterministic scores, history, duplicate-credit protection | Accept a score from anyone |

Cross-contract messages are asynchronous; two recovery calls (`WorkLog.retry_open_job`, `SkillVerifier.resend_finalization`) repair a dropped message. Cross-contract writes are authorized by addresses wired once by the deployer. After wiring, the owner has no remaining power and can renounce ownership. Details: [ARCHITECTURE.md](ARCHITECTURE.md).

## Evidence model

1. The claim stores only normalized `https` URLs (no credentials, ports, IPs, private hosts), 2–5 of them, from **distinct registrable domains**. Free self-publishing hosts count as their platform, not per user: every `*.github.io` page, `raw.githubusercontent.com` and `github.com` are one source, as are all `*.netlify.app` or `*.vercel.app` sites. Two pages an agent can create for free on the same platform therefore cannot satisfy the two-source rule.
2. During `evaluate`, the leader **and every validator** independently fetch every source (text capped at 16 000 characters) and judge each one: `supports`, `contradicts`, `irrelevant`, `unavailable` or `duplicate` (identical content behind two URLs counts once).
3. A `supports` or `contradicts` judgment only counts if its quote is an exact substring of the page text that node fetched. A fabricated quote is downgraded to `irrelevant` in code.
4. A verdict is derived from the statuses by a fixed rule, never by a submitter label.

## Consensus model

`SkillVerifier.evaluate` uses `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` with module-level functions that capture no contract state.

* For the first hour only the agent may trigger `evaluate` (the challenger for a re-evaluation); afterwards anyone may, so third parties cannot front-run the agent.
* The leader runs the full pipeline and returns a proposed verdict plus per-source details.
* Each validator **re-runs the full pipeline itself**, with its own fetches and its own model call, and accepts only if its own verdict is **exactly equal** to the leader's. Page bytes and quotes are not compared, because honest fetches differ slightly.
* GenLayer's protocol decides whether enough validators accepted; if not, the transaction fails, no state changes, and the claim stays `VERIFYING`.
* A validator accepts the leader's result only if (1) the leader's per-source statuses are well-formed and produce the leader's verdict, (2) the validator's own independent verdict is identical, and (3) every `supports`/`contradicts` quote the leader reports is an exact substring **of that same source in the validator's own fetch** and passes the relevance gate. A leader therefore cannot get fabricated or misattributed quotes stored. No page hash is stored: a leader-reported hash could not be checked, because honest page bytes differ between fetches.
* **Relevance gate (code, not model).** A quote only counts if it shares at least two content words with the claimed task and expected result, so a quote that is merely an injected instruction on the page cannot count as evidence.
* **Settlement waits for finality.** Score recording and bond release are sent with `on="finalized"`, so an appeal of the finalizing transaction cannot leave an irreversible score behind. Only `open_job` (job creation: a duplicate is rejected and an orphan job cannot finalize or score) uses `on="accepted"`, and `finalize` additionally requires WorkLog to still show the claim as `VERIFYING`.

## Scoring

Start 500, range 0–1000, integer arithmetic only.

| Finalized verdict | Change |
|---|---|
| PASS (fresh work) | +10 (+2 for repeated work) |
| FAIL | −30 |
| INSUFFICIENT_EVIDENCE | −2 |

Score-farming protection (a PASS earns **0** instead of +10 when any of these holds; it is still verified and recorded as `DUPLICATE_WORK` / `DAILY_CAP`):

* The task's content words (stopwords removed) overlap ≥ 80% with a credited PASS by the same agent in the last 7 days, measured against the *smaller* of the two word sets, so padding a reused task with extra words does not evade the check.
* Work that resembles an earlier credited task earns a **decayed +2** instead of +10 (`REPEAT_WORK`): similarity is checked against the last 20 credited works, and an exact repeat (same content words, any order) is remembered for the last 400 credited works. Recurring genuine work still counts a little; farming the same task with fresh links is worth one fifth.
* Fewer than 2 of its evidence keys (`registrable-domain+path`, query stripped, so `a.example.com/x` and `b.example.com/x` are the same key) are new to that agent within 7 days.
* The agent already gained +30 that UTC day.

"Translate the report into French" and "… into German" are different work and both earn credit. Near-identical claims are also rejected at submission while one is still open, and exact duplicates (agent + task + source set) are always rejected. Legitimate repeated work remains possible: it is accepted, verified, and earns the decayed rate after 7 days. An identical claim (same agent, task and sources) is rejected permanently.

## Challenge mechanism

After a verdict, a 48-hour window (constructor parameter, 60 s – 7 days) opens. Anyone with a refundable bond (0.05 GEN) and a 20–500 character reason may challenge **once**. The challenge triggers one independent re-evaluation (all validators re-fetch). That result is final. A challenge is *upheld* (bond returned) if the verdict changes, otherwise the bond is forfeited. Stuck verifications and challenges expire after 24 hours. Full state machine: [ARCHITECTURE.md](ARCHITECTURE.md).

## Repository layout

```
contracts/   worklog.py, skill_verifier.py, score_registry.py   (deploy-ready, no comments)
frontend/    index.html, app.js, lib.js, config.js               (hash-routed, mobile-first)
docs/        copy of frontend/ served by GitHub Pages
tests/       offline suite, SDK stub, frontend tests
scripts/     check_contracts.py, build_release.py, live/        (deploy + live scenarios)
docs: README, ARCHITECTURE, THREAT_MODEL, SECURITY, TESTING, DEPLOYMENT
```

Contract files contain only the two required header lines followed by code: GenLayer Studio has been observed to reject heavily commented contracts, so all documentation lives outside them.

## Local setup and tests

No third-party Python packages are needed.

```bash
python3 scripts/check_contracts.py                         # deploy-readiness rules
python3 -m unittest discover -s tests -t tests -v          # 208 offline tests
node --test tests/frontend/lib.test.mjs                    # frontend helpers
python3 scripts/build_release.py                           # dist/ + SHA-256 manifest
```

Frontend: serve `frontend/` with any static server, put the three deployed addresses in `frontend/config.js`, and open it with an injected wallet configured for GenLayer Studio. See [TESTING.md](TESTING.md).

## Deployment and live verification

[DEPLOYMENT.md](DEPLOYMENT.md) contains copy-paste tables for GenLayer Studio and the scripted flow (`scripts/live`, also runnable from the manual GitHub Action). Live scenarios use real public pages: a PASS case, a FAIL case, an INSUFFICIENT_EVIDENCE case, a challenge, finalization, score reads. Verdicts depend on live pages and a live model, so each run prints the expected verdict next to the observed one.

## Honest status

The three contracts were deployed and exercised end to end on GenLayer Studio (test build, 300 s challenge window): submit, open_job, evaluate with validator consensus, challenge and re-evaluation, finalize, score recording, claim closing, bond refunds and withdraw all worked, and PASS, FAIL and INSUFFICIENT_EVIDENCE verdicts were each observed. Addresses and measurements are in LIVE_RESULTS.md.

Not covered by the live run: the recovery calls (retry_open_job, resend_finalization) were never needed, and finality on a production network was not measured. The offline suite runs against a hand-written SDK stub, so it complements the live run and does not replace it. No third-party audit has been done.

scripts/live and the live GitHub Action are written against genlayer-js but were not executed; pin the version after the first successful run.

MIT licensed. Author: Mary1270.
