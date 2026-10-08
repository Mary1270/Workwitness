import test from "node:test";
import assert from "node:assert/strict";
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
} from "../../frontend/lib.js";

test("esc neutralises markup and quotes", () => {
  assert.equal(esc('<img src=x onerror="a()">'), "&lt;img src=x onerror=&quot;a()&quot;&gt;");
  assert.equal(esc("a&b'c"), "a&amp;b&#39;c");
  assert.equal(esc(null), "");
});

test("address helpers", () => {
  assert.ok(isAddress("0x" + "a1".repeat(20)));
  assert.ok(!isAddress("0x123"));
  assert.ok(!isAddress(undefined));
  assert.equal(shortAddr("0x" + "a1".repeat(20)), "0xa1a1a1…a1a1a1");
  assert.equal(shortAddr("0xabc"), "0xabc");
});

test("parseJson falls back on bad input", () => {
  assert.deepEqual(parseJson("[1,2]", []), [1, 2]);
  assert.deepEqual(parseJson("nope", []), []);
  assert.deepEqual(parseJson("null", {}), {});
});

test("time and GEN formatting", () => {
  assert.equal(fmtTime(0), "—");
  assert.equal(fmtTime(1800000000), "2027-01-15 08:00 UTC");
  assert.equal(fmtGen(10n ** 16n), "0.01 GEN");
  assert.equal(fmtGen(0), "0 GEN");
  assert.equal(fmtGen(3n * 10n ** 18n), "3 GEN");
  assert.equal(toWei("0.05"), 5n * 10n ** 16n);
  assert.equal(toWei("2"), 2n * 10n ** 18n);
  assert.throws(() => toWei("abc"));
  assert.throws(() => toWei("1.0000000000000000001"));
});

test("verdict, state and source labels", () => {
  assert.equal(verdictLabel("PASS"), "PASS");
  assert.equal(verdictLabel("INSUFFICIENT_EVIDENCE"), "INSUFFICIENT EVIDENCE");
  assert.equal(verdictLabel(""), "NOT DECIDED");
  assert.equal(verdictClass("FAIL"), "fail");
  assert.equal(verdictClass("x"), "none");
  assert.match(stateLabel("SUBMITTED"), /not yet verified/);
  assert.equal(stateLabel("???"), "???");
  assert.match(sourceStatusLabel("duplicate"), /counted once/);
  assert.equal(sourceStatusLabel("zzz"), "Not evaluated");
});

test("routing", () => {
  assert.deepEqual(parseRoute(""), { name: "home", arg: "" });
  assert.deepEqual(parseRoute("#/agents"), { name: "agents", arg: "" });
  assert.deepEqual(parseRoute("#/claim/12"), { name: "claim", arg: "12" });
  assert.deepEqual(parseRoute("#/agent/0xabc"), { name: "agent", arg: "0xabc" });
  assert.deepEqual(parseRoute("#/claim"), { name: "home", arg: "" });
  assert.deepEqual(parseRoute("#/nonsense/1"), { name: "home", arg: "" });
});

test("source parsing and href safety", () => {
  assert.deepEqual(parseSources("https://a.example.com/x, https://b.example.org/y\nhttps://c.example.net"), [
    "https://a.example.com/x",
    "https://b.example.org/y",
    "https://c.example.net",
  ]);
  assert.equal(safeHref("https://ok.example.com/a"), "https://ok.example.com/a");
  assert.equal(safeHref("javascript:alert(1)"), "");
  assert.equal(safeHref('https://x.example.com/"onmouseover="a'), "");
});

test("score reasons are readable", () => {
  assert.match(describeScoreReason("DUPLICATE_WORK"), /no credit/);
  assert.equal(describeScoreReason("SCORED"), "Score applied");
  assert.match(describeScoreReason("REPEAT_WORK"), /reduced rate/);
});
