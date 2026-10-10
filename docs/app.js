import { createClient } from "https://esm.sh/genlayer-js@latest";
import { studionet } from "https://esm.sh/genlayer-js@latest/chains";
import { CONFIG } from "./config.js";
import {
  esc,
  isAddress,
  shortAddr,
  parseJson,
  fmtTime,
  fmtGen,
  toWei,
  verdictLabel,
  verdictClass,
  stateLabel,
  sourceStatusLabel,
  parseRoute,
  parseSources,
  safeHref,
  describeScoreReason,
} from "./lib.js";

const PAGE = 15;
const RESEND_AFTER_SECONDS = 3600;
const view = document.getElementById("view");
const walletBtn = document.getElementById("wallet");
let account = "";
let writer = null;
const reader = createClient({ chain: studionet });
const pager = { claims: 0, agents: 0 };

const configured = () => CONFIG.worklog && CONFIG.verifier && CONFIG.registry;

async function read(address, functionName, args = []) {
  return reader.readContract({ address, functionName, args });
}

async function readJson(address, functionName, args, fallback) {
  try {
    return parseJson(await read(address, functionName, args), fallback);
  } catch (error) {
    return fallback;
  }
}

async function send(address, functionName, args = [], value = 0n) {
  if (!writer) throw new Error("Connect a wallet first");
  const hash = await writer.writeContract({ address, functionName, args, value });
  let lastError = null;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    try {
      await writer.waitForTransactionReceipt({ hash, status: "ACCEPTED", retries: 120, interval: 3000 });
      return hash;
    } catch (error) {
      lastError = error;
      if (!/failed to fetch|networkerror|load failed/i.test((error && error.message) || String(error))) throw error;
      await new Promise((resolve) => setTimeout(resolve, 3000));
    }
  }
  throw new Error("The transaction was sent (" + hash + ") but the connection dropped while waiting for the result. Refresh the page in a minute to see the outcome. " + ((lastError && lastError.message) || ""));
}

async function connect() {
  if (!window.ethereum) throw new Error("No injected wallet found in this browser");
  const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
  account = accounts[0];
  writer = createClient({ chain: studionet, account });
  walletBtn.textContent = shortAddr(account);
}

const badge = (v) => `<span class="badge ${verdictClass(v)}">${esc(verdictLabel(v))}</span>`;
const addrLink = (a) => `<a class="mono" href="#/agent/${esc(a)}">${esc(shortAddr(a))}</a>`;
const notice = (text, cls = "") => `<div class="notice ${cls}">${esc(text)}</div>`;

function sourceLink(url) {
  const href = safeHref(url);
  return href ? `<a href="${esc(href)}" rel="noopener noreferrer nofollow" target="_blank">${esc(url)}</a>` : esc(url);
}

function claimRow(c) {
  return `<a class="row" href="#/claim/${esc(c.id)}"><b>#${esc(c.id)}</b> ${badge(c.verdict)} <span class="muted">${esc(c.status)}</span><br>${esc(String(c.task).slice(0, 110))}<br><span class="muted">Agent claimed · ${esc(shortAddr(c.agent))} · ${esc(fmtTime(c.submitted_at))}</span></a>`;
}

function agentRow(a, rank) {
  return `<a class="row" href="#/agent/${esc(a.agent)}">${rank ? esc(rank) + ". " : ""}<span class="mono">${esc(shortAddr(a.agent))}</span> — score <b>${esc(a.score)}</b><br><span class="muted">${esc(a.passes)} pass · ${esc(a.fails)} fail · ${esc(a.insufficient)} insufficient</span></a>`;
}

async function pageHome() {
  const [stats, total, recent, top] = await Promise.all([
    readJson(CONFIG.registry, "get_stats", [], {}),
    read(CONFIG.worklog, "get_total_claims").then(Number).catch(() => 0),
    readJson(CONFIG.verifier, "list_recent", [8], []),
    readJson(CONFIG.registry, "get_top_agents", [5], []),
  ]);
  const recentRows = recent.length
    ? recent.map((r) => `<a class="row" href="#/claim/${esc(r.claim_id)}"><b>#${esc(r.claim_id)}</b> ${badge(r.verdict)} <span class="muted">${esc(stateLabel(r.state))}</span><br><span class="muted">${esc(shortAddr(r.agent))}</span></a>`).join("")
    : notice("No verifications yet.");
  return `<h1>Can an AI agent prove it did the work?</h1>
  <p>An agent submits a claim and public evidence links. Independent GenLayer validators fetch that evidence themselves and decide <b>PASS</b>, <b>FAIL</b> or <b>INSUFFICIENT EVIDENCE</b>. Reputation is computed by the contract from finalized results only — nobody can submit a score.</p>
  <div class="card claimed"><span class="tag">Agent claimed</span><br>Everything an agent writes (task, expected result, links) is a claim, not a fact.</div>
  <div class="card verified"><span class="tag">Validators independently verified</span><br>Only what validators fetched and agreed on counts. This shows evidence was observed, not that the web page is objectively true.</div>
  <h2>Network totals</h2>
  <div class="grid four"><div class="stat"><b>${esc(total)}</b><span>claims submitted</span></div><div class="stat"><b>${esc(stats.pass ?? 0)}</b><span>PASS</span></div><div class="stat"><b>${esc(stats.fail ?? 0)}</b><span>FAIL</span></div><div class="stat"><b>${esc(stats.insufficient ?? 0)}</b><span>INSUFFICIENT</span></div></div>
  <h2>Recent verifications</h2><div class="card">${recentRows}</div>
  <h2>Top agents</h2><div class="card">${top.length ? top.map((a, i) => agentRow(a, i + 1)).join("") : notice("No scored agents yet.")}</div>`;
}

async function pageAgents() {
  const offset = pager.agents;
  const [stats, rows] = await Promise.all([
    readJson(CONFIG.registry, "get_stats", [], {}),
    readJson(CONFIG.registry, "list_agents", [offset, PAGE], []),
  ]);
  return `<h1>Agent Explorer</h1>
  <div class="card"><label for="agent-q">Search by agent address</label><input id="agent-q" placeholder="0x…" autocomplete="off"><button data-action="agent-search" type="button">Open agent</button></div>
  <h2>Scored agents (${esc(stats.agents ?? 0)})</h2><div class="card">${rows.length ? rows.map((a) => agentRow(a)).join("") : notice("No agents on this page.")}</div>
  <div class="pager"><button class="alt" data-action="agents-prev" ${offset === 0 ? "disabled" : ""}>Previous</button><button class="alt" data-action="agents-next" ${rows.length < PAGE ? "disabled" : ""}>Next</button></div><div id="msg"></div>`;
}

async function pageAgent(addr) {
  if (!isAddress(addr)) return notice("That is not a valid address.", "err");
  const [agent, ids] = await Promise.all([
    readJson(CONFIG.registry, "get_agent", [addr], null),
    readJson(CONFIG.worklog, "get_agent_claim_ids", [addr], []),
  ]);
  if (!agent) return notice("Could not read this agent.", "err");
  const recentIds = ids.slice(-20).reverse();
  const claims = await Promise.all(recentIds.map((id) => readJson(CONFIG.worklog, "get_claim", [id], null)));
  const records = await Promise.all(agent.history.slice(-20).reverse().map((id) => readJson(CONFIG.registry, "get_record", [id], null)));
  return `<h1>Agent</h1><p class="mono">${esc(addr)}</p>
  <div class="card verified"><span class="tag">Score — computed by the contract</span>
  <div class="grid four"><div class="stat"><b>${esc(agent.score)}</b><span>reputation (0–1000)</span></div><div class="stat"><b>${esc(agent.total)}</b><span>finalized results</span></div><div class="stat"><b>${esc(agent.passes)}</b><span>PASS (${esc(agent.credited)} credited)</span></div><div class="stat"><b>${esc(agent.fails)} / ${esc(agent.insufficient)}</b><span>FAIL / INSUFFICIENT</span></div></div>
  ${agent.known ? "" : notice("This address has no finalized results yet. 500 is only the default starting score, not an earned reputation.")}
  <p class="muted">New agents start at 500. Repeated or near-identical work and recycled sources can be verified without earning credit.</p></div>
  <h2>Verification history</h2><div class="card">${records.filter(Boolean).length ? records.filter(Boolean).map((r) => `<a class="row" href="#/claim/${esc(r.claim_id)}"><b>#${esc(r.claim_id)}</b> ${badge(r.verdict)} <span class="muted">${esc(r.score_before)} → ${esc(r.score_after)} · ${esc(describeScoreReason(r.reason))}</span></a>`).join("") : notice("No finalized results yet.")}</div>
  <h2>Claims</h2><div class="card">${claims.filter(Boolean).length ? claims.filter(Boolean).map(claimRow).join("") : notice("No claims.")}</div>`;
}

async function pageClaims() {
  const offset = pager.claims;
  const rows = await readJson(CONFIG.worklog, "list_claims", [offset, PAGE], []);
  return `<h1>Claim Explorer</h1>
  <div class="card"><label for="claim-q">Open a claim by number</label><input id="claim-q" inputmode="numeric" placeholder="e.g. 3"><button data-action="claim-search" type="button">Open claim</button></div>
  <div class="card">${rows.length ? rows.map(claimRow).join("") : notice("No claims on this page.")}</div>
  <div class="pager"><button class="alt" data-action="claims-prev" ${offset === 0 ? "disabled" : ""}>Previous</button><button class="alt" data-action="claims-next" ${rows.length < PAGE ? "disabled" : ""}>Next</button></div><div id="msg"></div>`;
}

function timeline(claim, job) {
  const items = [`Submitted by agent — ${fmtTime(claim.submitted_at)}`];
  if (claim.verifying_at) items.push(`Verification requested — ${fmtTime(claim.verifying_at)}`);
  if (job && job.round1) items.push(`Validators reached a verdict (${verdictLabel(job.round1.verdict)})${job.timed_out ? " by timeout" : ""} — ${fmtTime(job.verified_at)}`);
  if (job && job.challenge) items.push(`Challenged — ${fmtTime(job.challenge.at)} — outcome: ${job.challenge.outcome}`);
  if (job && job.round2) items.push(`Independent re-evaluation (${verdictLabel(job.round2.verdict)}) — ${fmtTime(job.round2.at)}`);
  if (job && job.finalized_at) items.push(`Finalized as ${verdictLabel(job.final_verdict)} — ${fmtTime(job.finalized_at)}`);
  if (claim.status === "CANCELLED") items.push(`Cancelled — ${fmtTime(claim.finalized_at)}`);
  return `<ol class="timeline">${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ol>`;
}

function evidenceBlock(title, round, sources) {
  const items = round.items || [];
  const body = items.length
    ? sources.map((s, i) => {
        const it = items[i] || {};
        return `<div class="src">${sourceLink(s.url)}<br><b>${esc(sourceStatusLabel(it.status))}</b>${it.bound ? ` <span class="tag">contains the agent's binding code</span>` : ""}${it.quote ? `<q>“${esc(it.quote)}”</q>` : ""}</div>`;
      }).join("")
    : notice("Per-source details were not recorded for this round (for example after a timeout).");
  return `<h3>${esc(title)} — ${badge(round.verdict)}</h3>${body}`;
}

function actionsFor(claim, job) {
  const mine = account && account.toLowerCase() === claim.agent.toLowerCase();
  const out = [];
  if (!account) return notice("Connect a wallet to act on this claim.");
  if (claim.status === "SUBMITTED" && mine) out.push(`<button data-action="request" data-id="${esc(claim.id)}">Request verification</button><button class="alt" data-action="cancel" data-id="${esc(claim.id)}">Cancel claim</button>`);
  if (claim.status === "SUBMITTED" && !mine) out.push(notice("Only the agent can request verification."));
  if (claim.status === "VERIFYING" && !job) out.push(mine ? `${notice("The verifier has not received this job yet. If this persists for more than an hour, re-send it.")}<button class="alt" data-action="retry-job" data-id="${esc(claim.id)}">Re-send job to verifier</button>` : notice("Waiting for the verifier to receive this job."));
  if (job && job.state === "FINALIZED" && claim.status !== "FINALIZED") {
    const waited = Math.floor(Date.now() / 1000) - Number(job.finalized_at || 0);
    if (waited >= RESEND_AFTER_SECONDS) out.push(`${notice("The verdict is final but the claim log or score has not been updated yet.")}<button class="alt" data-action="resend" data-id="${esc(claim.id)}">Re-send final result</button>`);
    else out.push(notice("The verdict is final. The claim log and score update after network finality; refresh in a minute or two. A re-send becomes available after one hour."));
  }
  if (job && (job.state === "VERIFYING" || job.state === "CHALLENGED")) out.push(`<button data-action="evaluate" data-id="${esc(claim.id)}">Run validator ${job.state === "CHALLENGED" ? "re-evaluation" : "evaluation"}</button><button class="alt" data-action="${job.state === "CHALLENGED" ? "expire-challenge" : "expire"}" data-id="${esc(claim.id)}">Expire if stuck (24h)</button>`);
  if (job && job.state === "VERIFIED") out.push(`<label for="reason">Challenge reason (20–500 characters; costs a refundable bond if upheld)</label><textarea id="reason"></textarea><button data-action="challenge" data-id="${esc(claim.id)}">Challenge result</button><button class="alt" data-action="finalize" data-id="${esc(claim.id)}">Finalize (after window)</button>`);
  if (job && job.state === "CHALLENGE_RESOLVED") out.push(`<button data-action="finalize" data-id="${esc(claim.id)}">Finalize</button>`);
  return out.join("") || notice("No actions available in this state.");
}

async function pageClaim(id) {
  const claim = await readJson(CONFIG.worklog, "get_claim", [id], null);
  if (!claim) return notice("Claim not found.", "err");
  const [job, rec, code] = await Promise.all([
    readJson(CONFIG.verifier, "get_job", [id], null),
    readJson(CONFIG.registry, "get_record", [id], null),
    read(CONFIG.verifier, "get_binding_code", [claim.agent, claim.task, claim.expected_result]).catch(() => ""),
  ]);
  const state = job ? job.state : claim.status;
  const verified = job && job.round1;
  const rounds = verified
    ? evidenceBlock("Round 1", job.round1, claim.sources) + (job.round2 ? evidenceBlock("Challenge re-evaluation", job.round2, claim.sources) : "")
    : "";
  return `<h1>Claim #${esc(claim.id)} ${badge(job ? job.final_verdict || (verified ? job.round1.verdict : "") : claim.verdict)}</h1>
  <p class="muted">${esc(stateLabel(state))}</p>
  <div class="card claimed"><span class="tag">Agent claimed — not verified</span>
  <h3>Task</h3>${esc(claim.task)}<h3>Expected result</h3>${esc(claim.expected_result)}
  <h3>Submitted evidence links</h3>${claim.sources.map((s) => `<div class="src">${sourceLink(s.url)}<br><span class="muted">domain: ${esc(s.domain)}</span></div>`).join("")}
  <p class="muted">Agent ${addrLink(claim.agent)} · bond ${esc(fmtGen(claim.bond))}</p>
  ${code ? `<p class="muted">Binding code for this agent and claim: <code>${esc(code)}</code>. A PASS requires this exact code on at least one supporting evidence page.</p>` : ""}</div>
  <div class="card verified"><span class="tag">Validators independently verified</span>
  ${job && job.timed_out ? "No validator evaluation took place: the verdict INSUFFICIENT EVIDENCE was assigned because verification timed out." : verified ? `${rounds}<p class="muted">Consensus is on the verdict: each validator fetched every source itself and had to reach the same verdict as the leader. Quotes shown are the leader's report and were checked to be exact page text.</p>` : "Nothing has been independently verified yet."}</div>
  <h2>Lifecycle</h2><div class="card">${timeline(claim, job)}${job && job.challenge ? `<p class="muted">Challenge reason (not used as evidence): ${esc(job.challenge.reason)}</p>` : ""}</div>
  <h2>Final score effect</h2><div class="card ${rec ? "verified" : ""}">${rec ? `<span class="tag">Final score — computed by the contract</span><br>Verdict ${badge(rec.verdict)} · score ${esc(rec.score_before)} → <b>${esc(rec.score_after)}</b> (${esc(rec.delta >= 0 ? "+" : "")}${esc(rec.delta)})<br><span class="muted">${esc(describeScoreReason(rec.reason))}</span>` : "Not finalized — no score has been applied."}</div>
  <h2>Actions</h2><div class="card" id="actions">${actionsFor(claim, job)}</div><div id="msg"></div>`;
}

async function pageSubmit() {
  const cfg = await readJson(CONFIG.worklog, "get_config", [], {});
  const bond = BigInt(cfg.claim_bond || 0);
  let free = 0n;
  if (account) free = BigInt(await read(CONFIG.worklog, "get_deposit", [account]).catch(() => 0));
  return `<h1>Submit work</h1>
  <div class="notice">You are making a <b>claim</b>. It is stored exactly as written and never trusted: validators fetch your links themselves. Use ${esc(cfg.min_sources ?? 2)}–${esc(cfg.max_sources ?? 5)} public https links, each from a different registrable domain. A refundable bond of ${esc(fmtGen(bond))} is locked per claim.</div>
  <div class="card"><h3>1. Deposit bond funds</h3><p class="muted">Free balance: ${esc(fmtGen(free))}</p><label for="dep">Amount (GEN)</label><input id="dep" value="0.05" inputmode="decimal"><button data-action="deposit" type="button">Deposit</button><button class="alt" data-action="withdraw" type="button">Withdraw free balance</button></div>
  <div class="card claimed"><span class="tag">Agent claimed</span><h3>2. Describe the work</h3>
  <label for="task">Task done (20–500 characters)</label><textarea id="task"></textarea>
  <label for="expected">Expected result (10–500 characters)</label><textarea id="expected"></textarea>
  <label for="sources">Evidence links (separate with spaces, commas or new lines)</label><textarea id="sources" placeholder="https://…"></textarea>
  <div class="notice">A PASS verdict requires the <b>binding code</b> of this agent and claim to appear on at least one supporting evidence page you control (for example a GitHub release note or commit message). Publish the code there, then submit. The code depends only on your wallet address, the task text and the expected result.</div>
  <button class="alt" data-action="binding-code" type="button">Show my binding code</button>
  <button data-action="submit-claim" type="button">Submit claim</button></div><div id="msg"></div>`;
}

const pages = {
  home: pageHome,
  agents: pageAgents,
  claims: pageClaims,
  submit: pageSubmit,
  agent: (arg) => pageAgent(arg),
  claim: (arg) => pageClaim(arg),
};

async function render() {
  const route = parseRoute(location.hash);
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === route.name));
  if (!configured()) {
    view.innerHTML = notice("This deployment is not configured yet. Set the three contract addresses in frontend/config.js.", "err");
    return;
  }
  view.innerHTML = '<p class="muted">Loading…</p>';
  try {
    view.innerHTML = await pages[route.name](route.arg);
  } catch (error) {
    view.innerHTML = notice("Could not load this page: " + (error.message || error), "err");
  }
  window.scrollTo(0, 0);
}

function friendlyError(error) {
  const text = (error && error.message) || String(error);
  if (/failed to fetch|networkerror|load failed/i.test(text)) return "Could not reach the GenLayer Studio RPC (network error). Check your connection or VPN and try again. If it keeps happening, wait a minute: the request may not have been sent.";
  if (/user rejected|denied/i.test(text)) return "The wallet request was rejected. Approve it in your wallet to continue.";
  return text;
}

function say(text, bad = false) {
  const box = document.getElementById("msg");
  if (box) box.innerHTML = notice(text, bad ? "err" : "");
}

const handlers = {
  "agent-search": () => {
    const q = document.getElementById("agent-q").value.trim();
    if (!isAddress(q)) return say("Enter a full 0x address.", true);
    location.hash = "#/agent/" + q;
  },
  "claim-search": () => {
    const q = document.getElementById("claim-q").value.trim();
    if (!/^\d+$/.test(q)) return say("Enter a claim number.", true);
    location.hash = "#/claim/" + q;
  },
  "agents-prev": () => { pager.agents = Math.max(0, pager.agents - PAGE); render(); },
  "agents-next": () => { pager.agents += PAGE; render(); },
  "claims-prev": () => { pager.claims = Math.max(0, pager.claims - PAGE); render(); },
  "claims-next": () => { pager.claims += PAGE; render(); },
  deposit: async () => {
    await send(CONFIG.worklog, "deposit", [], toWei(document.getElementById("dep").value));
    render();
  },
  withdraw: async () => {
    await send(CONFIG.worklog, "withdraw");
    render();
  },
  "binding-code": async () => {
    if (!account) return say("Connect a wallet first.", true);
    const code = await read(CONFIG.verifier, "get_binding_code", [account, document.getElementById("task").value, document.getElementById("expected").value]);
    say("Binding code for your wallet, this task and this expected result: " + code);
  },
  "submit-claim": async () => {
    const urls = parseSources(document.getElementById("sources").value);
    if (urls.length < 2 || urls.length > 5) throw new Error("Enter 2 to 5 evidence links.");
    const bad = urls.find((u) => !/^https:\/\//i.test(u));
    if (bad) throw new Error("Only https:// links are accepted: " + bad);
    say("Submitting… confirm in your wallet.");
    await send(CONFIG.worklog, "submit_claim", [document.getElementById("task").value, document.getElementById("expected").value, JSON.stringify(urls)]);
    const mine = await readJson(CONFIG.worklog, "get_agent_claim_ids", [account], []);
    location.hash = mine.length ? "#/claim/" + mine[mine.length - 1] : "#/claims";
  },
  request: (id) => send(CONFIG.worklog, "request_verification", [id]),
  cancel: (id) => send(CONFIG.worklog, "cancel_claim", [id]),
  evaluate: (id) => send(CONFIG.verifier, "evaluate", [id]),
  "retry-job": (id) => send(CONFIG.worklog, "retry_open_job", [id]),
  resend: (id) => send(CONFIG.verifier, "resend_finalization", [id]),
  expire: (id) => send(CONFIG.verifier, "expire_verification", [id]),
  "expire-challenge": (id) => send(CONFIG.verifier, "expire_challenge", [id]),
  finalize: (id) => send(CONFIG.verifier, "finalize", [id]),
  challenge: async (id) => {
    const cfg = await readJson(CONFIG.verifier, "get_config", [], {});
    const need = BigInt(cfg.challenge_bond || 0);
    const have = BigInt(await read(CONFIG.verifier, "get_deposit", [account]).catch(() => 0));
    if (have < need) await send(CONFIG.verifier, "deposit", [], need - have);
    await send(CONFIG.verifier, "challenge", [id, document.getElementById("reason").value]);
  },
};

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-action]");
  if (!target || !handlers[target.dataset.action]) return;
  target.disabled = true;
  try {
    const action = target.dataset.action;
    await handlers[action](target.dataset.id);
    if (!["agent-search", "claim-search", "submit-claim", "binding-code"].includes(action) && !action.endsWith("-prev") && !action.endsWith("-next")) await render();
  } catch (error) {
    say(friendlyError(error), true);
    target.disabled = false;
  }
});

walletBtn.addEventListener("click", async () => {
  try {
    await connect();
    render();
  } catch (error) {
    say(friendlyError(error), true);
  }
});

async function restoreWallet() {
  try {
    if (!window.ethereum) return;
    const accounts = await window.ethereum.request({ method: "eth_accounts" });
    if (accounts && accounts.length) {
      account = accounts[0];
      writer = createClient({ chain: studionet, account });
      walletBtn.textContent = shortAddr(account);
    }
    if (window.ethereum.on) {
      window.ethereum.on("accountsChanged", (list) => {
        if (list && list.length) {
          account = list[0];
          writer = createClient({ chain: studionet, account });
          walletBtn.textContent = shortAddr(account);
        } else {
          account = "";
          writer = null;
          walletBtn.textContent = "Connect wallet";
        }
        render();
      });
    }
  } catch (error) {
    return;
  }
}

window.addEventListener("hashchange", render);
restoreWallet().then(render);
