# Deployment

Wallets used below:

| Name | Address |
|---|---|
| Deployer / Agent | `0x6921398611F6c4793D745348660912D44d4F8479` |
| Challenger (any second Studio account) | `0x9Bf4a51B888C6FFBF337a25BF3179B07A6259128` |

## A. GenLayer Studio (no terminal needed)

Paste each file from `contracts/` as-is (two header lines, then code). If Studio reports an invalid runner, change only line 1 to the version your Studio shows.

### Deploy and wire

| Step | Wallet | Where | Action | Arguments |
|---|---|---|---|---|
| 1 | `0x6921398611F6c4793D745348660912D44d4F8479` | `score_registry.py` | Deploy | none |
| 2 | `0x6921398611F6c4793D745348660912D44d4F8479` | `worklog.py` | Deploy | none |
| 3 | `0x6921398611F6c4793D745348660912D44d4F8479` | `skill_verifier.py` | Deploy | `300` for live tests, `172800` for production |
| 4 | `0x6921398611F6c4793D745348660912D44d4F8479` | WorkLog | `set_verifier` | `<SkillVerifier address>` |
| 5 | `0x6921398611F6c4793D745348660912D44d4F8479` | ScoreRegistry | `set_verifier` | `<SkillVerifier address>` |
| 6 | `0x6921398611F6c4793D745348660912D44d4F8479` | SkillVerifier | `wire` | `<WorkLog address>`, `<ScoreRegistry address>` |
| 7 | any | each contract | `get_config` | confirm the three addresses match |
| 8 (production) | `0x6921398611F6c4793D745348660912D44d4F8479` | all three | `renounce_ownership` | none |

### Live test: one claim, challenged, finalized

Evidence is real and public. Verdicts depend on live pages and a live model.

| Step | Wallet | Contract | Method | Arguments | Value |
|---|---|---|---|---|---|
| 1 | `0x6921398611F6c4793D745348660912D44d4F8479` | WorkLog | `deposit` | none | 0.1 GEN (the Studio Value field is in GEN, not wei) |
| 1b | any | SkillVerifier | `get_binding_code` | the agent wallet · `Publish Python 3.11.6 security release to the public` · `Python 3.11.6 was publicly released in October 2023` | — |
| 1c | the agent wallet | GitHub | publish a file in a repo the agent controls whose text is `Python 3.11.6 was publicly released in October 2023. Ref <binding code>`; use its raw url as the first source | — | — |
| 2 | `0x6921398611F6c4793D745348660912D44d4F8479` | WorkLog | `submit_claim` | `Publish Python 3.11.6 security release to the public` · `Python 3.11.6 was publicly released in October 2023` · `["<raw url of the file from 1c>","https://www.python.org/downloads/release/python-3116/"]` | 0 |
| 3 | `0x6921398611F6c4793D745348660912D44d4F8479` | WorkLog | `request_verification` | `1` | 0 |
| 4 | `0x6921398611F6c4793D745348660912D44d4F8479` | SkillVerifier | `evaluate` | `1` | 0 |
| 5 | any | SkillVerifier | `get_job` | `1` | — |
| 6 | `0x9Bf4a51B888C6FFBF337a25BF3179B07A6259128` | SkillVerifier | `deposit` | none | 0.05 GEN |
| 7 | `0x9Bf4a51B888C6FFBF337a25BF3179B07A6259128` | SkillVerifier | `challenge` | `1` · `Re-checking that the cited release pages still show the stated result` | 0 |
| 8 | `0x6921398611F6c4793D745348660912D44d4F8479` | SkillVerifier | `evaluate` | `1` | 0 |
| 9 | `0x6921398611F6c4793D745348660912D44d4F8479` | SkillVerifier | `finalize` | `1` | 0 |
| 9b | any | SkillVerifier | `get_job` → state `FINALIZED`; then wait until the `finalize` transaction itself shows FINALIZED in Studio (the score and bond messages are sent on finality) | `1` | — |
| 10 | any | ScoreRegistry | `get_agent` (after 9b) | `0x6921398611F6c4793D745348660912D44d4F8479` | — |
| 11 | any | ScoreRegistry | `get_stats`, `list_recent` | `5` | — |
| 12 | `0x6921398611F6c4793D745348660912D44d4F8479` | WorkLog | `withdraw` | none | 0 |
| 13 | `0x9Bf4a51B888C6FFBF337a25BF3179B07A6259128` | SkillVerifier | `withdraw` | none | 0 |

A PASS needs the binding code on a supporting page the agent controls; without it two supporting sources give INSUFFICIENT_EVIDENCE. FAIL and INSUFFICIENT_EVIDENCE cases need no code (use new task text and new URLs each time, wait 60 s between submissions):

| Case | Task | Expected result | Sources |
|---|---|---|---|
| FAIL | `Release Python 3.11.0 as a stable version` | `Python 3.11.0 release date was Oct. 24, 2019` | `["https://www.python.org/downloads/release/python-3110/","https://devcenter.heroku.com/changelog-items/2696"]` |
| INSUFFICIENT_EVIDENCE | `Publish the quarterly gardening report for the northern region` | `The quarterly gardening report for the northern region is published` | `["https://example.com/","https://www.iana.org/help/example-domains"]` |

For an unchallenged claim, call `finalize` only after the challenge window (300 s on the test build). The challenge in step 7 must be sent within that window.

Recovery (only if a step stalls):

| Situation | Wallet | Contract | Method | Arguments |
|---|---|---|---|---|
| `get_job` says "job not found" more than 1 h after step 3 | `0x6921398611F6c4793D745348660912D44d4F8479` | WorkLog | `retry_open_job` | `1` |
| Job is `FINALIZED`, its transaction is FINALIZED, but `get_claim` still says `VERIFYING` | `0x6921398611F6c4793D745348660912D44d4F8479` | SkillVerifier | `resend_finalization` (needs 1 h after `finalize`; max 3 times) | `1` |
| `evaluate` keeps failing for 24 h | `0x6921398611F6c4793D745348660912D44d4F8479` | SkillVerifier | `expire_verification` | `1` |

Afterwards put the three addresses into `frontend/config.js`, publish `frontend/` (GitHub Pages works), and open it with a wallet on Studio.

## B. Scripted (same flow)

```bash
cd scripts/live && npm install
export GENLAYER_PRIVATE_KEY=<throwaway testnet key>   # never commit it
export CHALLENGE_WINDOW_SECONDS=300
node deploy.mjs                                       # prints the three addresses
export WORKLOG_ADDRESS=... VERIFIER_ADDRESS=... REGISTRY_ADDRESS=...
node scenarios.mjs                                    # PASS, FAIL, INSUFFICIENT, challenge, finalize, queries
```

The same scripts run from the manual **live-test** GitHub Action (secret `GENLAYER_PRIVATE_KEY`; repository variables for the addresses and window). These scripts depend on `genlayer-js`, which is not pinned here; after the first successful run, commit the lockfile and pin the version. They have not been executed in the environment where this repository was authored.

## C. Release build

`python3 scripts/build_release.py` copies the three contracts to `dist/` with a SHA-256 manifest, so the deployed code can be compared to a tagged release.
