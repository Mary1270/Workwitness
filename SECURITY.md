# Security

## What this system guarantees

* A verdict is accepted only when validators, each using its own fetches and model call, reproduce it, and every quote shown in the UI was found by every validator in its own copy of that page.
* Scores and bonds are settled only after the finalizing transaction is final (`on="finalized"`), so an appeal cannot leave an irreversible score behind. Consequently scores and bond releases appear after GenLayer finality, not immediately.
* Submitters cannot supply a verdict, quote or score.
* Only the wired contracts can change claim status or scores, and each result is applied once.
* Reputation is replayable from the permanent per-claim records.

## What this system does not guarantee (read this)

1. **It is not a truth oracle.** WorkWitness shows that independent validators *observed* public web content that supports or contradicts a claim. It does not establish that the content is true. An agent controlling two public sites can publish matching false statements. Distinct-domain and duplicate-content rules, bonds and the challenge window make this harder and visible; they do not make it impossible.
2. **Model judgment is fallible.** The model can misread a real page, be influenced by text on a page, or misjudge dates. Code checks (exact quote, status rules, INSUFFICIENT_EVIDENCE default) limit the damage; they do not remove it.
3. **Verdicts are not bound to page bytes.** Pages can change after a verdict. Only the challenge window re-checks them.
4. **Per-source details are only partly validator-backed.** Quotes are verified by every validator against its own fetch; the individual labels of non-decisive sources (`irrelevant`, `unavailable`, `duplicate`) are leader-reported audit data. No page hash is stored.
5. **Domain independence is approximate.** The registrable-domain function uses small built-in suffix tables, not the full public-suffix list. Different-looking domains may share an owner.
6. **Sybil agents** are limited only by bonds.
7. **Cross-contract messages are asynchronous.** The contracts are written to be idempotent and expose manual recovery calls (`retry_open_job`, `resend_finalization`), but nothing retries automatically.
7a. **Scores reflect only claims an agent chose to verify.** Unstarted or cancelled claims carry no penalty, and one bonded challenge can buy a second model evaluation.
8. **Unverified against the real SDK in CI.** The offline tests use a hand-written stub of the GenLayer SDK. They match patterns previously confirmed on GenLayer Studio, but the stub is not the real runtime. Differences (for example consensus thresholds, storage behavior, `datetime` semantics) could exist.
9. **Payouts to wallets use the pattern proven on GenLayer Studio** (`get_contract_at(wallet).emit_transfer(value=...)`, used in earlier live-tested projects). Current GenLayer documentation shows an EVM-interface pattern for transfers to externally owned accounts on a real network, and Studio simulates value transfers, so test `withdraw` live and be ready to switch patterns for a non-Studio network.
10. **No audit.** The code has not been independently audited. It is a protocol prototype and must not be described as bug-free or fully secure.

## Operational advice

* Deploy, wire and verify addresses with the `get_config` views before calling `renounce_ownership`.
* Never put private keys or seed phrases in this repository, in issues, or in `.env.example`. The live GitHub Action reads the key from an encrypted repository secret only; use a throwaway testnet key.
* Treat every URL shown in the UI as untrusted content: it is displayed as text and linked only if it is `https`.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository (Security → Report a vulnerability), or contact the maintainer, Mary1270, through GitHub. Please include the contract, method and a reproduction against the offline suite where possible.
