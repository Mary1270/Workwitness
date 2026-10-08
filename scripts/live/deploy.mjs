import { makeClient, deploy, write, view, env } from "./lib.mjs";

const window = Number(env("CHALLENGE_WINDOW_SECONDS", false) || 300);
const { client, account } = makeClient();
console.log(`deployer ${account.address}`);

const worklog = await deploy(client, "worklog.py", [], "deploy WorkLog");
const registry = await deploy(client, "score_registry.py", [], "deploy ScoreRegistry");
const verifier = await deploy(client, "skill_verifier.py", [window], `deploy SkillVerifier (window ${window}s)`);

await write(client, worklog, "set_verifier", [verifier], 0n, "WorkLog.set_verifier");
await write(client, registry, "set_verifier", [verifier], 0n, "ScoreRegistry.set_verifier");
await write(client, verifier, "wire", [worklog, registry], 0n, "SkillVerifier.wire");

console.log(JSON.stringify(await view(client, worklog, "get_config"), null, 2));
console.log(JSON.stringify(await view(client, verifier, "get_config"), null, 2));
console.log("\nAdd to .env / repository variables:");
console.log(`WORKLOG_ADDRESS=${worklog}\nVERIFIER_ADDRESS=${verifier}\nREGISTRY_ADDRESS=${registry}`);
