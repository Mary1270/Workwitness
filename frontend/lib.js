export function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function isAddress(value) {
  return /^0x[0-9a-fA-F]{40}$/.test(String(value ?? "").trim());
}

export function shortAddr(addr) {
  const text = String(addr ?? "");
  return text.length > 14 ? text.slice(0, 8) + "…" + text.slice(-6) : text;
}

export function parseJson(raw, fallback) {
  try {
    const value = JSON.parse(raw);
    return value === null || value === undefined ? fallback : value;
  } catch (error) {
    return fallback;
  }
}

export function fmtTime(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n) || n <= 0) return "—";
  return new Date(n * 1000).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

export function fmtGen(wei) {
  const text = BigInt(wei ?? 0).toString().padStart(19, "0");
  const whole = text.slice(0, -18).replace(/^0+(?=\d)/, "");
  const frac = text.slice(-18).replace(/0+$/, "");
  return (whole || "0") + (frac ? "." + frac : "") + " GEN";
}

export function toWei(gen) {
  const match = /^(\d+)(?:\.(\d{1,18}))?$/.exec(String(gen).trim());
  if (!match) throw new Error("Enter a valid GEN amount");
  return BigInt(match[1]) * 10n ** 18n + BigInt((match[2] || "").padEnd(18, "0"));
}

const VERDICTS = {
  PASS: ["PASS", "pass"],
  FAIL: ["FAIL", "fail"],
  INSUFFICIENT_EVIDENCE: ["INSUFFICIENT EVIDENCE", "insufficient"],
};

export function verdictLabel(verdict) {
  return (VERDICTS[verdict] || ["NOT DECIDED", "none"])[0];
}

export function verdictClass(verdict) {
  return (VERDICTS[verdict] || ["", "none"])[1];
}

const STATES = {
  SUBMITTED: "Submitted by agent — not yet verified",
  VERIFYING: "Verification requested — waiting for validators",
  VERIFIED: "Validators reached a verdict — challenge window open",
  CHALLENGED: "Challenged — independent re-evaluation pending",
  CHALLENGE_RESOLVED: "Re-evaluation complete — ready to finalize",
  FINALIZED: "Final — score applied",
  CANCELLED: "Cancelled by agent",
};

export function stateLabel(state) {
  return STATES[state] || String(state || "Unknown");
}

const SOURCE_STATUS = {
  supports: "Validators saw text supporting the claim",
  contradicts: "Validators saw text contradicting the claim",
  irrelevant: "Page fetched; nothing decisive",
  unavailable: "Could not be fetched or evaluated",
  duplicate: "Same content as an earlier source — counted once",
};

export function sourceStatusLabel(status) {
  return SOURCE_STATUS[status] || "Not evaluated";
}

export function parseRoute(hash) {
  const parts = String(hash || "").replace(/^#\/?/, "").split("/").filter(Boolean);
  const name = parts[0] || "home";
  const arg = parts[1] ? decodeURIComponent(parts[1]) : "";
  if (["home", "agents", "claims", "submit"].includes(name)) return { name, arg: "" };
  if ((name === "agent" || name === "claim") && arg) return { name, arg };
  return { name: "home", arg: "" };
}

export function parseSources(text) {
  return String(text ?? "")
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function safeHref(url) {
  return /^https:\/\/[^\s"'<>]+$/.test(String(url ?? "")) ? url : "";
}

export function describeScoreReason(reason) {
  const map = {
    SCORED: "Score applied",
    DUPLICATE_WORK: "Verified, but no credit: same or near-identical work or recycled sources within 7 days",
    REPEAT_WORK: "Credited at a reduced rate: the same kind of work was already credited earlier",
    DAILY_CAP: "Verified, but no credit: daily gain cap reached",
  };
  return map[reason] || reason || "";
}
