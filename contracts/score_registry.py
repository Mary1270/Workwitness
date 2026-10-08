# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

import datetime
import hashlib
import json

VERDICTS = ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE")
START_SCORE = 500
MAX_SCORE = 1000
PASS_DELTA = 10
REPEAT_DELTA = 2
FAIL_DELTA = -30
INSUFFICIENT_DELTA = -2
DAILY_GAIN_CAP = 30
REPEAT_WINDOW = 604800
SIMILARITY_PCT = 80
MIN_FRESH_KEYS = 2
MAX_RECENT_WORK = 20
MAX_FINGERPRINTS = 400
HISTORY_CAP = 100
MAX_PAGE = 50
MAX_SCAN = 500
MAX_TOKENS = 128
MIN_COMPARE = 3
MAX_KEYS = 5


def _fail(message):
    raise gl.vm.UserError(message)


def _now():
    return int(datetime.datetime.now().timestamp())


def _addr(value):
    try:
        return str(Address(value))
    except Exception:
        _fail("invalid address")


def similar(a, b):
    left = set(a)
    right = set(b)
    if len(left) == 0 or len(right) == 0:
        return False
    smaller = min(len(left), len(right))
    if smaller < MIN_COMPARE:
        return left == right
    return len(left & right) * 100 >= SIMILARITY_PCT * smaller


def work_fingerprint(tokens):
    if len(tokens) == 0:
        return ""
    return hashlib.sha256(" ".join(sorted(tokens)).encode("utf-8")).hexdigest()[:16]


def clamp(score):
    return max(0, min(MAX_SCORE, score))


def parse_list(raw, limit, label):
    try:
        data = json.loads(raw)
    except Exception:
        _fail(label + " must be JSON")
    if not isinstance(data, list) or len(data) > limit:
        _fail(label + " is invalid")
    for item in data:
        if not isinstance(item, str) or len(item) > 320:
            _fail(label + " is invalid")
    return data


def new_agent(agent):
    return {
        "agent": agent,
        "score": START_SCORE,
        "total": 0,
        "passes": 0,
        "fails": 0,
        "insufficient": 0,
        "credited": 0,
        "day": 0,
        "gain": 0,
        "work": [],
        "fp": [],
        "history": [],
    }


class ScoreRegistry(gl.Contract):
    owner: str
    verifier: str
    total_results: u256
    pass_total: u256
    fail_total: u256
    insufficient_total: u256
    agents: TreeMap[str, str]
    records: TreeMap[str, str]
    agent_list: DynArray[str]
    recent: DynArray[str]

    def __init__(self):
        self.owner = str(gl.message.sender_address)

    @gl.public.write
    def set_verifier(self, verifier: str) -> None:
        if self.owner == "" or str(gl.message.sender_address) != self.owner:
            _fail("only the owner can wire the verifier")
        if self.verifier != "":
            _fail("verifier is already set")
        self.verifier = _addr(verifier)

    @gl.public.write
    def renounce_ownership(self) -> None:
        if self.owner == "" or str(gl.message.sender_address) != self.owner:
            _fail("only the owner can renounce ownership")
        self.owner = ""

    @gl.public.write
    def record_result(
        self,
        claim_id: str,
        agent: str,
        verdict: str,
        work_tokens_json: str,
        evidence_keys_json: str,
    ) -> None:
        if self.verifier == "" or str(gl.message.sender_address) != self.verifier:
            _fail("only the wired SkillVerifier can record results")
        if claim_id in self.records:
            _fail("result already recorded for this claim")
        if verdict not in VERDICTS:
            _fail("invalid verdict")
        who = _addr(agent)
        tokens = parse_list(work_tokens_json, MAX_TOKENS, "work tokens")
        keys = parse_list(evidence_keys_json, MAX_KEYS, "evidence keys")
        now = _now()
        if who in self.agents:
            rec = json.loads(self.agents[who])
        else:
            rec = new_agent(who)
            self.agent_list.append(who)
        delta = 0
        reason = "SCORED"
        if verdict == "PASS":
            recent = [w for w in rec["work"] if now - w["at"] < REPEAT_WINDOW]
            used = set()
            for w in recent:
                used |= set(w["k"])
            duplicate = any(similar(tokens, w["t"]) for w in recent)
            if duplicate or len(set(keys) - used) < MIN_FRESH_KEYS:
                reason = "DUPLICATE_WORK"
            else:
                fp = work_fingerprint(tokens)
                repeat = (fp != "" and fp in rec["fp"]) or any(similar(tokens, w["t"]) for w in rec["work"])
                base = REPEAT_DELTA if repeat else PASS_DELTA
                if repeat:
                    reason = "REPEAT_WORK"
                day = now // 86400
                if rec["day"] != day:
                    rec["day"] = day
                    rec["gain"] = 0
                delta = min(base, DAILY_GAIN_CAP - rec["gain"])
                if delta <= 0:
                    delta = 0
                    reason = "DAILY_CAP"
                else:
                    rec["gain"] += delta
                    rec["work"].append({"t": tokens, "k": keys, "at": now})
                    rec["work"] = rec["work"][-MAX_RECENT_WORK:]
                    if fp != "":
                        rec["fp"] = (rec["fp"] + [fp])[-MAX_FINGERPRINTS:]
                    rec["credited"] += 1
            rec["passes"] += 1
            self.pass_total = u256(int(self.pass_total) + 1)
        elif verdict == "FAIL":
            delta = FAIL_DELTA
            rec["fails"] += 1
            self.fail_total = u256(int(self.fail_total) + 1)
        else:
            delta = INSUFFICIENT_DELTA
            rec["insufficient"] += 1
            self.insufficient_total = u256(int(self.insufficient_total) + 1)
        before = rec["score"]
        rec["score"] = clamp(before + delta)
        rec["total"] += 1
        rec["history"] = (rec["history"] + [claim_id])[-HISTORY_CAP:]
        self.agents[who] = json.dumps(rec, sort_keys=True)
        self.records[claim_id] = json.dumps(
            {
                "claim_id": claim_id,
                "agent": who,
                "verdict": verdict,
                "delta": rec["score"] - before,
                "reason": reason,
                "score_before": before,
                "score_after": rec["score"],
                "at": now,
            },
            sort_keys=True,
        )
        self.total_results = u256(int(self.total_results) + 1)
        self.recent.append(claim_id)

    def _public_agent(self, rec):
        return {
            "agent": rec["agent"],
            "known": True,
            "score": rec["score"],
            "total": rec["total"],
            "passes": rec["passes"],
            "fails": rec["fails"],
            "insufficient": rec["insufficient"],
            "credited": rec["credited"],
            "history": rec["history"],
        }

    @gl.public.view
    def get_agent(self, agent: str) -> str:
        who = _addr(agent)
        if who not in self.agents:
            return json.dumps(
                {
                    "agent": who,
                    "known": False,
                    "score": START_SCORE,
                    "total": 0,
                    "passes": 0,
                    "fails": 0,
                    "insufficient": 0,
                    "credited": 0,
                    "history": [],
                }
            )
        return json.dumps(self._public_agent(json.loads(self.agents[who])), sort_keys=True)

    @gl.public.view
    def get_record(self, claim_id: str) -> str:
        if claim_id not in self.records:
            return ""
        return self.records[claim_id]

    @gl.public.view
    def get_stats(self) -> str:
        return json.dumps(
            {
                "total": int(self.total_results),
                "pass": int(self.pass_total),
                "fail": int(self.fail_total),
                "insufficient": int(self.insufficient_total),
                "agents": len(self.agent_list),
            },
            sort_keys=True,
        )

    @gl.public.view
    def list_agents(self, offset: int, limit: int) -> str:
        if offset < 0 or limit < 0:
            _fail("offset and limit must be non-negative")
        limit = min(limit, MAX_PAGE)
        total = len(self.agent_list)
        out = []
        for i in range(offset, min(offset + limit, total)):
            rec = json.loads(self.agents[self.agent_list[i]])
            out.append(self._public_agent(rec))
        return json.dumps(out)

    @gl.public.view
    def get_top_agents(self, limit: int) -> str:
        if limit < 0:
            _fail("limit must be non-negative")
        limit = min(limit, MAX_PAGE)
        total = min(len(self.agent_list), MAX_SCAN)
        rows = []
        for i in range(total):
            rec = json.loads(self.agents[self.agent_list[i]])
            rows.append((-rec["score"], -rec["credited"], rec["agent"], rec))
        rows.sort(key=lambda row: (row[0], row[1], row[2]))
        return json.dumps([self._public_agent(row[3]) for row in rows[:limit]])

    @gl.public.view
    def list_recent(self, limit: int) -> str:
        if limit < 0:
            _fail("limit must be non-negative")
        limit = min(limit, MAX_PAGE)
        total = len(self.recent)
        out = []
        for i in range(min(limit, total)):
            out.append(json.loads(self.records[self.recent[total - 1 - i]]))
        return json.dumps(out)

    @gl.public.view
    def get_config(self) -> str:
        return json.dumps(
            {
                "start_score": START_SCORE,
                "max_score": MAX_SCORE,
                "pass_delta": PASS_DELTA,
                "repeat_delta": REPEAT_DELTA,
                "fail_delta": FAIL_DELTA,
                "insufficient_delta": INSUFFICIENT_DELTA,
                "daily_gain_cap": DAILY_GAIN_CAP,
                "repeat_window": REPEAT_WINDOW,
                "similarity_pct": SIMILARITY_PCT,
                "min_fresh_keys": MIN_FRESH_KEYS,
                "verifier": self.verifier,
                "owner": self.owner,
            },
            sort_keys=True,
        )
