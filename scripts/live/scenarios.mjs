import { makeClient, write, view, env, sleep } from "./lib.mjs";

const worklog = env("WORKLOG_ADDRESS");
const verifier = env("VERIFIER_ADDRESS");
const registry = env("REGISTRY_ADDRESS");
const window = Number(env("CHALLENGE_WINDOW_SECONDS", false) || 300);
const { client, account } = makeClient();
const me = account.address;

const BOND = 10n ** 16n;
const CHALLENGE_BOND = 5n * 10n ** 16n;
const COOLDOWN = 61;

const SCENARIOS = [
  {
    name: "PASS",
    task: "Publish Python 3.11.6 security release to the public",
    expected: "Python 3.11.6 was publicly released in October 2023",
    sources: ["https://www.python.org/downloads/release/python-3116/", "https://devcenter.heroku.com/changelog-items/2696"],
    challenge: true,
  },
  {
    name: "FAIL",
    task: "Release Python 3.11.0 as a stable version",
    expected: "Python 3.11.0 release date was Oct. 24, 2019",
    sources: ["https://www.python.org/downloads/release/python-3110/", "https://devcenter.heroku.com/changelog-items/2696"],
  },
  {
    name: "INSUFFICIENT_EVIDENCE",
    task: "Publish the quarterly gardening report for the northern region",
    expected: "The quarterly gardening report for the northern region is published",
    sources: ["https://example.com/", "https://www.iana.org/help/example-domains"],
  },
];

async function newestClaimId() {
  const ids = await view(client, worklog, "get_agent_claim_ids", [me]);
  return String(ids[ids.length - 1]);
}

async function waitForJob(id) {
  for (let i = 0; i < 30; i += 1) {
    try {
      return await view(client, verifier, "get_job", [id]);
    } catch (error) {
      await sleep(5);
    }
  }
  throw new Error(`job ${id} never reached the verifier; run WorkLog.retry_open_job after one hour`);
}

await write(client, worklog, "deposit", [], BOND * 10n, "fund claim bonds");
await write(client, verifier, "deposit", [], CHALLENGE_BOND * 2n, "fund challenge bond");

const results = [];
for (const scenario of SCENARIOS) {
  await write(client, worklog, "submit_claim", [scenario.task, scenario.expected, JSON.stringify(scenario.sources)], 0n, `submit ${scenario.name}`);
  const id = await newestClaimId();
  await write(client, worklog, "request_verification", [id], 0n, `request verification #${id}`);
  await waitForJob(id);
  await write(client, verifier, "evaluate", [id], 0n, `validators evaluate #${id}`);
  const job = await view(client, verifier, "get_job", [id]);
  console.log(`    #${id} expected ${scenario.name}, validators decided ${job.round1.verdict}`);
  console.log(`    per-source: ${job.round1.items.map((i) => i.status).join(", ") || "(details not recorded)"}`);
  if (scenario.challenge) {
    await write(client, verifier, "challenge", [id, "Re-checking that the cited release pages still show the stated result"], 0n, `challenge #${id} inside the window`);
    await write(client, verifier, "evaluate", [id], 0n, `independent re-evaluation #${id}`);
    const after = await view(client, verifier, "get_job", [id]);
    console.log(`    challenge outcome ${after.challenge.outcome}, final ${after.final_verdict}`);
  }
  results.push({ id, expected: scenario.name, observed: job.round1.verdict });
  await sleep(COOLDOWN);
}

console.log(`\nwaiting ${window + 5}s for the challenge windows to close`);
await sleep(window + 5);
for (const r of results) {
  r.final = await write(client, verifier, "finalize", [r.id], 0n, `finalize #${r.id}`).then(() => view(client, verifier, "get_job", [r.id])).then((j) => j.final_verdict);
}
const finalityWait = Number(env("FINALITY_WAIT_SECONDS", false) || 1800);
console.log(`\nscore and bond messages are sent on finality; polling up to ${finalityWait}s`);
const deadline = Date.now() + finalityWait * 1000;
for (const r of results) {
  while (true) {
    const record = await view(client, registry, "get_record", [r.id]);
    const claim = await view(client, worklog, "get_claim", [r.id]);
    r.claim_status = claim.status;
    r.score_delta = record ? record.delta : "pending finality";
    if (record || Date.now() > deadline) break;
    await sleep(20);
  }
}
console.table(results);
console.log("agent", JSON.stringify(await view(client, registry, "get_agent", [me]), null, 2));
console.log("stats", JSON.stringify(await view(client, registry, "get_stats"), null, 2));
const mismatches = results.filter((r) => r.expected !== r.observed);
if (mismatches.length) {
  console.log(`\n${mismatches.length} verdict(s) differ from the expectation. Live pages and models change; inspect get_job before treating this as a bug.`);
}
