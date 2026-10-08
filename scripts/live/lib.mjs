import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createClient, createAccount } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

const here = dirname(fileURLToPath(import.meta.url));
export const root = join(here, "..", "..");

export function env(name, required = true) {
  const value = process.env[name] || "";
  if (required && !value) throw new Error(`Missing environment variable ${name}`);
  return value;
}

export function makeClient() {
  const key = env("GENLAYER_PRIVATE_KEY");
  const account = createAccount(key.startsWith("0x") ? key : "0x" + key);
  const client = createClient({ chain: studionet, account });
  return { client, account };
}

export const code = (name) => readFileSync(join(root, "contracts", name), "utf8");

export async function wait(client, hash, label) {
  const receipt = await client.waitForTransactionReceipt({ hash, status: "ACCEPTED", retries: 200, interval: 4000 });
  console.log(`ok  ${label}`);
  return receipt;
}

export async function deploy(client, file, args, label) {
  const hash = await client.deployContract({ code: code(file), args, leaderOnly: false });
  const receipt = await wait(client, hash, label);
  const address = receipt?.data?.contract_address ?? receipt?.contractAddress ?? receipt?.to_address;
  if (!address) throw new Error(`Could not read the deployed address for ${label}; inspect the receipt in Studio`);
  console.log(`    ${label} at ${address}`);
  return address;
}

export async function write(client, address, functionName, args = [], value = 0n, label = functionName) {
  const hash = await client.writeContract({ address, functionName, args, value });
  return wait(client, hash, label);
}

export async function view(client, address, functionName, args = []) {
  const raw = await client.readContract({ address, functionName, args });
  try {
    return typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch (error) {
    return raw;
  }
}

export const sleep = (seconds) => new Promise((resolve) => setTimeout(resolve, seconds * 1000));
