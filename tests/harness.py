import datetime as _real_datetime
import importlib.util
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "genlayer_stub"))

import genlayer  # noqa: E402
from genlayer import RT, ConsensusFailure, UserError  # noqa: E402,F401

PASS = "PASS"
FAIL = "FAIL"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"

OWNER = "0x" + "01" * 20
AGENT = "0x" + "a1" * 20
AGENT2 = "0x" + "a2" * 20
CHALLENGER = "0x" + "c1" * 20
STRANGER = "0x" + "99" * 20

DAY = 86400
WINDOW = 172800
CLAIM_BOND = 10**16
CHALLENGE_BOND = 5 * 10**16


class Clock:
    now = 1_800_000_000


class _FakeDatetime:
    @classmethod
    def now(cls, tz=None):
        return _real_datetime.datetime.fromtimestamp(Clock.now, tz=_real_datetime.timezone.utc)


_FAKE_MODULE = types.SimpleNamespace(datetime=_FakeDatetime, timezone=_real_datetime.timezone)


def load_contract(name):
    path = os.path.join(ROOT, "contracts", name + ".py")
    spec = importlib.util.spec_from_file_location("ap_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.datetime = _FAKE_MODULE
    return module


worklog_mod = load_contract("worklog")
verifier_mod = load_contract("skill_verifier")
registry_mod = load_contract("score_registry")


def page(*lines):
    return " ".join(lines)


def keyword_llm(prompt):
    body = prompt.split("<<<PAGE\n", 1)[1].rsplit("\nPAGE>>>", 1)[0]
    quote = " ".join(body.split())[:200]
    if "RESULT: SUCCESS" in body:
        return {"status": "supports", "quote": quote}
    if "RESULT: FAILURE" in body:
        return {"status": "contradicts", "quote": quote}
    return {"status": "irrelevant", "quote": ""}


def fabricating_llm(prompt):
    return {"status": "supports", "quote": "this sentence was never on the page at all"}


def broken_llm(prompt):
    raise RuntimeError("model unavailable")


CLAIM_WORDS = "the quarterly report translation"


def good(url, code=None):
    ref = code if code is not None else verifier_mod.binding_code(AGENT, TASK, EXPECTED)
    return "The audit log at " + url + " says " + CLAIM_WORDS + " was published, RESULT: SUCCESS confirmed. Ref " + ref + "."


def good_unbound(url):
    return "The audit log at " + url + " says " + CLAIM_WORDS + " was published, RESULT: SUCCESS confirmed."


def bad(url):
    return "The audit log at " + url + " says " + CLAIM_WORDS + " was not published, RESULT: FAILURE confirmed."


def neutral(url):
    return "The page at " + url + " discusses unrelated gardening topics only."


TASK = "Translate the quarterly report into French and publish it"
EXPECTED = "A French translation of the quarterly report is published online"
URL_A = "https://alpha.example.com/report"
URL_B = "https://beta.example.org/report"
URL_C = "https://gamma.example.net/report"


def sources_json(*urls):
    return json.dumps(list(urls))


class System:
    def __init__(self, window=WINDOW, validators=5):
        RT.reset()
        RT.n_validators = validators
        RT.llm = keyword_llm
        Clock.now = 1_800_000_000
        self.wl = RT.deploy(worklog_mod.WorkLog, (), OWNER)
        self.vf = RT.deploy(verifier_mod.SkillVerifier, (window,), OWNER)
        self.sr = RT.deploy(registry_mod.ScoreRegistry, (), OWNER)
        self.call(OWNER, self.wl, "set_verifier", self.vf)
        self.call(OWNER, self.vf, "wire", self.wl, self.sr)
        self.call(OWNER, self.sr, "set_verifier", self.vf)

    def call(self, sender, addr, method, *args, value=0):
        snap = RT.snapshot()
        try:
            return RT.invoke(addr, method, args, sender, value, "write")
        except Exception:
            RT.stack = []
            RT.restore(snap)
            raise

    def view(self, addr, method, *args):
        return RT.invoke(addr, method, args, STRANGER, 0, "view")

    def jview(self, addr, method, *args):
        return json.loads(self.view(addr, method, *args))

    def advance(self, seconds):
        Clock.now += seconds

    def set_pages(self, pages):
        RT.pages = dict(pages)

    def fund_agent(self, who=AGENT, amount=10 * CLAIM_BOND):
        self.call(who, self.wl, "deposit", value=amount)

    def fund_verifier(self, who, amount=CHALLENGE_BOND * 2):
        self.call(who, self.vf, "deposit", value=amount)

    def submit(self, who=AGENT, task=TASK, expected=EXPECTED, urls=(URL_A, URL_B)):
        self.fund_agent(who)
        self.advance(61)
        return self.call(who, self.wl, "submit_claim", task, expected, sources_json(*urls))

    def start(self, claim_id, who=AGENT):
        self.call(who, self.wl, "request_verification", claim_id)

    def evaluate(self, claim_id, who=AGENT):
        return self.call(who, self.vf, "evaluate", claim_id)

    def run_to_verified(self, who=AGENT, task=TASK, urls=(URL_A, URL_B), verdict_pages=None):
        pages = verdict_pages or {u: good(u) for u in urls}
        RT.pages.update(pages)
        claim_id = self.submit(who, task=task, urls=urls)
        self.start(claim_id, who)
        self.evaluate(claim_id, who)
        return claim_id

    def finalize_after_window(self, claim_id):
        self.advance(WINDOW + 1)
        return self.call(STRANGER, self.vf, "finalize", claim_id)

    def contract_balance(self, addr):
        return RT.balances.get(addr, 0)


class Base(unittest.TestCase):
    def setUp(self):
        self.s = System()

    def assertRevert(self, fn, fragment=None):
        with self.assertRaises(UserError) as ctx:
            fn()
        if fragment:
            self.assertIn(fragment, str(ctx.exception))
