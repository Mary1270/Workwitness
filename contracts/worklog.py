# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

import datetime
import hashlib
import json
import re
from urllib.parse import urlsplit

CLAIM_BOND = 10**16
MAX_OPEN_CLAIMS = 3
SUBMIT_COOLDOWN = 60
TASK_MIN = 20
TASK_MAX = 500
EXPECTED_MIN = 10
EXPECTED_MAX = 500
MIN_SOURCES = 2
MAX_SOURCES = 5
MAX_URL_LEN = 300
MAX_SOURCES_JSON = 2000
MAX_TOKENS = 128
SIMILARITY_PCT = 80
MIN_COMPARE = 3
MAX_PAGE = 50
MAX_HISTORY = 200
RETRY_AFTER = 3600

CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
HOST_RE = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+")
TLD_RE = re.compile(r"[a-z]{2,63}|xn--[a-z0-9-]{1,59}")
STOPWORDS = {
    "the", "and", "for", "with", "into", "from", "that", "this", "was", "are", "has", "have",
    "its", "our", "all", "any", "not", "but", "then", "than", "will", "been", "were", "which",
    "who", "what", "when", "where", "onto", "over", "via", "per", "out", "had", "can", "also",
}

MULTI_SUFFIX = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au",
    "co.jp", "co.nz", "co.za", "com.br", "com.cn", "co.in", "com.mx", "com.tr",
}
FAMILY = {
    "githubusercontent.com": "github.com",
    "github.io": "github.com",
    "githubassets.com": "github.com",
    "gitlab.io": "gitlab.com",
    "firebaseapp.com": "web.app",
    "blogspot.com": "blogger.com",
}


def _fail(message):
    raise gl.vm.UserError(message)


def _now():
    return int(datetime.datetime.now().timestamp())


def _addr(value):
    try:
        return str(Address(value))
    except Exception:
        _fail("invalid address")


def clean_text(value, low, high, name):
    if not isinstance(value, str):
        _fail(name + " must be a string")
    if len(value) > high * 4:
        _fail(name + " is too long")
    if CONTROL.search(value):
        _fail(name + " contains control characters")
    text = " ".join(value.split())
    if len(text) < low or len(text) > high:
        _fail(name + " length must be between " + str(low) + " and " + str(high))
    return text


def registrable_domain(host):
    labels = host.split(".")
    if len(labels) < 2:
        return ""
    last_two = ".".join(labels[-2:])
    if last_two in MULTI_SUFFIX and len(labels) >= 3:
        return ".".join(labels[-3:])
    return FAMILY.get(last_two, last_two)


def normalize_url(raw):
    if not isinstance(raw, str):
        _fail("url must be a string")
    raw = raw.strip()
    if len(raw) == 0 or len(raw) > MAX_URL_LEN:
        _fail("url length is invalid")
    for ch in raw:
        if ord(ch) < 33 or ord(ch) > 126:
            _fail("url must be printable ascii without spaces")
    try:
        parts = urlsplit(raw)
        port = parts.port
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        _fail("url is malformed")
    if parts.scheme.lower() != "https":
        _fail("only https urls are accepted")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        _fail("urls with credentials are rejected")
    if port not in (None, 443):
        _fail("only the default https port is accepted")
    if not HOST_RE.fullmatch(host) or not TLD_RE.fullmatch(host.rsplit(".", 1)[-1]):
        _fail("url host is invalid")
    if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        _fail("private hosts are rejected")
    raw_path = parts.path or "/"
    path = re.sub(r"/{2,}", "/", raw_path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = parts.query
    url = "https://" + host + raw_path + ("?" + query if query else "")
    bare = host[4:] if host.startswith("www.") else host
    domain = registrable_domain(bare)
    if domain == "":
        _fail("url host is invalid")
    key = (domain + path).lower()
    return {"url": url, "domain": domain, "key": key}


def tokens_of(text):
    out = []
    for token in re.findall(r"[a-z0-9]{3,}", text.lower()):
        token = token[:32]
        if token in STOPWORDS:
            continue
        if token not in out:
            out.append(token)
        if len(out) >= MAX_TOKENS:
            break
    return out


def similar(a, b):
    left = set(a)
    right = set(b)
    if len(left) == 0 or len(right) == 0:
        return False
    smaller = min(len(left), len(right))
    if smaller < MIN_COMPARE:
        return left == right
    return len(left & right) * 100 >= SIMILARITY_PCT * smaller


def fingerprint(agent, task, keys):
    material = agent + "|" + task.lower() + "|" + ",".join(sorted(keys))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class WorkLog(gl.Contract):
    owner: str
    verifier: str
    next_claim_id: u256
    locked_total: u256
    claims: TreeMap[str, str]
    claim_state: TreeMap[str, str]
    fingerprints: TreeMap[str, str]
    agent_open: TreeMap[str, str]
    agent_claims: TreeMap[str, str]
    last_submit: TreeMap[str, u256]
    deposits: TreeMap[str, u256]

    def __init__(self):
        self.owner = str(gl.message.sender_address)

    def _bal(self, who):
        if who in self.deposits:
            return int(self.deposits[who])
        return 0

    def _load(self, store, key, label):
        if key not in store:
            _fail(label + " not found")
        return json.loads(store[key])

    def _open_list(self, agent):
        if agent in self.agent_open:
            return json.loads(self.agent_open[agent])
        return []

    def _drop_open(self, agent, claim_id):
        remaining = [c for c in self._open_list(agent) if c != claim_id]
        self.agent_open[agent] = json.dumps(remaining)

    def _only_verifier(self):
        if self.verifier == "" or str(gl.message.sender_address) != self.verifier:
            _fail("only the wired verifier can call this method")

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

    @gl.public.write.payable
    def deposit(self) -> None:
        amount = int(gl.message.value)
        if amount <= 0:
            _fail("deposit must be positive")
        who = str(gl.message.sender_address)
        self.deposits[who] = u256(self._bal(who) + amount)

    @gl.public.write
    def withdraw(self) -> int:
        who = str(gl.message.sender_address)
        amount = self._bal(who)
        if amount <= 0:
            _fail("nothing to withdraw")
        self.deposits[who] = u256(0)
        gl.get_contract_at(Address(who)).emit_transfer(value=u256(amount))
        return amount

    @gl.public.write
    def submit_claim(self, task: str, expected_result: str, sources_json: str) -> str:
        agent = str(gl.message.sender_address)
        now = _now()
        task_text = clean_text(task, TASK_MIN, TASK_MAX, "task")
        expected_text = clean_text(expected_result, EXPECTED_MIN, EXPECTED_MAX, "expected_result")
        if not isinstance(sources_json, str) or len(sources_json) > MAX_SOURCES_JSON:
            _fail("sources_json is too large")
        try:
            raw_sources = json.loads(sources_json)
        except Exception:
            _fail("sources_json must be a JSON array of urls")
        if not isinstance(raw_sources, list):
            _fail("sources_json must be a JSON array of urls")
        if len(raw_sources) < MIN_SOURCES or len(raw_sources) > MAX_SOURCES:
            _fail("between " + str(MIN_SOURCES) + " and " + str(MAX_SOURCES) + " sources are required")
        sources = []
        domains = []
        keys = []
        for raw in raw_sources:
            item = normalize_url(raw)
            if item["domain"] in domains:
                _fail("sources must come from distinct registrable domains")
            if item["key"] in keys:
                _fail("duplicate source")
            domains.append(item["domain"])
            keys.append(item["key"])
            sources.append(item)
        if self._bal(agent) < CLAIM_BOND:
            _fail("insufficient deposit for the claim bond")
        if agent in self.last_submit and now < int(self.last_submit[agent]) + SUBMIT_COOLDOWN:
            _fail("submission cooldown is active")
        open_ids = self._open_list(agent)
        if len(open_ids) >= MAX_OPEN_CLAIMS:
            _fail("too many open claims")
        fp = fingerprint(agent, task_text, keys)
        if fp in self.fingerprints and self.fingerprints[fp] != "":
            _fail("duplicate claim")
        tokens = tokens_of(task_text)
        for other_id in open_ids:
            other = json.loads(self.claims[other_id])
            if similar(tokens, other["tokens"]):
                _fail("a similar claim is already open")
        claim_id = str(int(self.next_claim_id) + 1)
        self.next_claim_id = u256(int(self.next_claim_id) + 1)
        self.deposits[agent] = u256(self._bal(agent) - CLAIM_BOND)
        self.locked_total = u256(int(self.locked_total) + CLAIM_BOND)
        record = {
            "id": claim_id,
            "agent": agent,
            "task": task_text,
            "expected_result": expected_text,
            "sources": sources,
            "tokens": tokens,
            "fingerprint": fp,
            "submitted_at": now,
            "bond": CLAIM_BOND,
        }
        self.claims[claim_id] = json.dumps(record, sort_keys=True)
        self.claim_state[claim_id] = json.dumps(
            {"status": "SUBMITTED", "verdict": "", "verifying_at": 0, "finalized_at": 0},
            sort_keys=True,
        )
        self.fingerprints[fp] = claim_id
        self.last_submit[agent] = u256(now)
        open_ids.append(claim_id)
        self.agent_open[agent] = json.dumps(open_ids)
        history = json.loads(self.agent_claims[agent]) if agent in self.agent_claims else []
        history = (history + [claim_id])[-MAX_HISTORY:]
        self.agent_claims[agent] = json.dumps(history)
        return claim_id

    @gl.public.write
    def cancel_claim(self, claim_id: str) -> None:
        record = self._load(self.claims, claim_id, "claim")
        state = self._load(self.claim_state, claim_id, "claim")
        if str(gl.message.sender_address) != record["agent"]:
            _fail("only the claim agent can cancel")
        if state["status"] != "SUBMITTED":
            _fail("only a SUBMITTED claim can be cancelled")
        state["status"] = "CANCELLED"
        state["finalized_at"] = _now()
        self.claim_state[claim_id] = json.dumps(state, sort_keys=True)
        self.fingerprints[record["fingerprint"]] = ""
        self._drop_open(record["agent"], claim_id)
        self.locked_total = u256(int(self.locked_total) - record["bond"])
        agent = record["agent"]
        self.deposits[agent] = u256(self._bal(agent) + record["bond"])

    @gl.public.write
    def request_verification(self, claim_id: str) -> None:
        record = self._load(self.claims, claim_id, "claim")
        state = self._load(self.claim_state, claim_id, "claim")
        if str(gl.message.sender_address) != record["agent"]:
            _fail("only the claim agent can request verification")
        if state["status"] != "SUBMITTED":
            _fail("claim is not in SUBMITTED state")
        if self.verifier == "":
            _fail("verifier is not wired")
        state["status"] = "VERIFYING"
        state["verifying_at"] = _now()
        self.claim_state[claim_id] = json.dumps(state, sort_keys=True)
        self._send_job(record)

    def _send_job(self, record):
        keys = [s["key"] for s in record["sources"]]
        gl.get_contract_at(Address(self.verifier)).emit(on="accepted").open_job(
            record["id"],
            record["agent"],
            record["task"],
            record["expected_result"],
            json.dumps(record["sources"], sort_keys=True),
            json.dumps(record["tokens"]),
            json.dumps(keys),
        )

    @gl.public.write
    def retry_open_job(self, claim_id: str) -> None:
        record = self._load(self.claims, claim_id, "claim")
        state = self._load(self.claim_state, claim_id, "claim")
        if str(gl.message.sender_address) != record["agent"]:
            _fail("only the claim agent can retry")
        if state["status"] != "VERIFYING":
            _fail("claim is not in VERIFYING state")
        if _now() < state["verifying_at"] + RETRY_AFTER:
            _fail("retry is not allowed yet")
        self._send_job(record)

    @gl.public.write
    def close_claim(self, claim_id: str, verdict: str) -> None:
        self._only_verifier()
        record = self._load(self.claims, claim_id, "claim")
        state = self._load(self.claim_state, claim_id, "claim")
        if state["status"] != "VERIFYING":
            _fail("claim is not in VERIFYING state")
        if verdict not in ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE"):
            _fail("invalid verdict")
        state["status"] = "FINALIZED"
        state["verdict"] = verdict
        state["finalized_at"] = _now()
        self.claim_state[claim_id] = json.dumps(state, sort_keys=True)
        self._drop_open(record["agent"], claim_id)
        self.locked_total = u256(int(self.locked_total) - record["bond"])
        agent = record["agent"]
        self.deposits[agent] = u256(self._bal(agent) + record["bond"])

    @gl.public.view
    def get_claim(self, claim_id: str) -> str:
        record = self._load(self.claims, claim_id, "claim")
        state = self._load(self.claim_state, claim_id, "claim")
        record.update(state)
        return json.dumps(record, sort_keys=True)

    @gl.public.view
    def get_total_claims(self) -> int:
        return int(self.next_claim_id)

    @gl.public.view
    def list_claims(self, offset: int, limit: int) -> str:
        total = int(self.next_claim_id)
        if offset < 0 or limit < 0:
            _fail("offset and limit must be non-negative")
        limit = min(limit, MAX_PAGE)
        out = []
        for i in range(offset, min(offset + limit, total)):
            claim_id = str(total - i)
            record = json.loads(self.claims[claim_id])
            state = json.loads(self.claim_state[claim_id])
            out.append(
                {
                    "id": claim_id,
                    "agent": record["agent"],
                    "task": record["task"],
                    "submitted_at": record["submitted_at"],
                    "status": state["status"],
                    "verdict": state["verdict"],
                }
            )
        return json.dumps(out)

    @gl.public.view
    def get_agent_claim_ids(self, agent: str) -> str:
        who = _addr(agent)
        if who in self.agent_claims:
            return self.agent_claims[who]
        return "[]"

    @gl.public.view
    def get_deposit(self, who: str) -> int:
        return self._bal(_addr(who))

    @gl.public.view
    def get_config(self) -> str:
        return json.dumps(
            {
                "claim_bond": CLAIM_BOND,
                "max_open_claims": MAX_OPEN_CLAIMS,
                "submit_cooldown": SUBMIT_COOLDOWN,
                "min_sources": MIN_SOURCES,
                "max_sources": MAX_SOURCES,
                "verifier": self.verifier,
                "owner": self.owner,
                "locked_total": int(self.locked_total),
            },
            sort_keys=True,
        )
