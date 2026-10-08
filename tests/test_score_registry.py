import json
import unittest

from harness import (
    AGENT,
    AGENT2,
    DAY,
    OWNER,
    RT,
    STRANGER,
    Base,
    Clock,
    registry_mod,
)

FAKE_VERIFIER = "0x" + "ee" * 20


class RegistryBase(Base):
    def setUp(self):
        super().setUp()
        self.reg = RT.deploy(registry_mod.ScoreRegistry, (), OWNER)
        self.s.call(OWNER, self.reg, "set_verifier", FAKE_VERIFIER)
        self.n = 0

    def record(self, verdict, agent=AGENT, tokens=None, keys=None, claim_id=None):
        self.n += 1
        claim_id = claim_id or str(self.n)
        tokens = tokens if tokens is not None else ["tok%d" % self.n, "word%d" % self.n, "item%d" % self.n]
        keys = keys if keys is not None else ["a%d.example.com/x" % self.n, "b%d.example.org/y" % self.n]
        self.s.call(FAKE_VERIFIER, self.reg, "record_result", claim_id, agent, verdict, json.dumps(tokens), json.dumps(keys))
        return json.loads(self.s.view(self.reg, "get_record", claim_id))

    def agent(self, who=AGENT):
        return json.loads(self.s.view(self.reg, "get_agent", who))


class ScoreMath(RegistryBase):
    def test_unknown_agent_has_start_score_and_no_history(self):
        a = self.agent()
        self.assertEqual((a["score"], a["total"], a["history"], a["known"]), (500, 0, [], False))
        self.record("PASS")
        self.assertTrue(self.agent()["known"])

    def test_pass_adds_ten(self):
        rec = self.record("PASS")
        self.assertEqual((rec["delta"], rec["score_after"], rec["reason"]), (10, 510, "SCORED"))

    def test_fail_subtracts_thirty(self):
        self.assertEqual(self.record("FAIL")["score_after"], 470)

    def test_insufficient_subtracts_two(self):
        self.assertEqual(self.record("INSUFFICIENT_EVIDENCE")["score_after"], 498)

    def test_counts_by_verdict(self):
        self.record("PASS")
        self.record("FAIL")
        self.record("INSUFFICIENT_EVIDENCE")
        a = self.agent()
        self.assertEqual((a["passes"], a["fails"], a["insufficient"], a["total"], a["credited"]), (1, 1, 1, 3, 1))
        stats = json.loads(self.s.view(self.reg, "get_stats"))
        self.assertEqual((stats["total"], stats["pass"], stats["fail"], stats["insufficient"], stats["agents"]), (3, 1, 1, 1, 1))

    def test_floor_at_zero(self):
        for _ in range(20):
            self.record("FAIL")
        self.assertEqual(self.agent()["score"], 0)
        rec = self.record("FAIL")
        self.assertEqual((rec["delta"], rec["score_after"]), (0, 0))

    def test_ceiling_at_one_thousand(self):
        for _ in range(60):
            for _ in range(3):
                self.record("PASS")
            Clock.now += DAY
        a = self.agent()
        self.assertEqual(a["score"], 1000)
        self.assertEqual(self.record("PASS")["delta"], 0)

    def test_score_is_replayable_from_records(self):
        outcomes = ["PASS", "FAIL", "PASS", "INSUFFICIENT_EVIDENCE", "PASS"]
        for verdict in outcomes:
            self.record(verdict)
        score = 500
        for claim_id in self.agent()["history"]:
            score += json.loads(self.s.view(self.reg, "get_record", claim_id))["delta"]
        self.assertEqual(score, self.agent()["score"])

    def test_no_method_accepts_a_score(self):
        for name in dir(registry_mod.ScoreRegistry):
            fn = getattr(registry_mod.ScoreRegistry, name)
            if getattr(fn, "_gl_kind", None) in ("write", "payable"):
                self.assertNotIn("score", fn.__code__.co_varnames[: fn.__code__.co_argcount])


class DuplicateAndFarming(RegistryBase):
    def test_identical_work_in_window_earns_nothing(self):
        tokens = ["translate", "report", "french", "publish"]
        self.record("PASS", tokens=tokens)
        rec = self.record("PASS", tokens=tokens, keys=["n1.example.com/z", "n2.example.org/z"])
        self.assertEqual((rec["delta"], rec["reason"]), (0, "DUPLICATE_WORK"))

    def test_near_duplicate_task_earns_nothing(self):
        base = ["translate", "quarterly", "report", "into", "french", "and", "publish", "online"]
        self.record("PASS", tokens=base)
        rec = self.record("PASS", tokens=base + ["today"], keys=["n1.example.com/z", "n2.example.org/z"])
        self.assertEqual(rec["reason"], "DUPLICATE_WORK")

    def test_padded_task_is_a_duplicate(self):
        base = ["translate", "quarterly", "report", "french", "publish"]
        self.record("PASS", tokens=base)
        rec = self.record("PASS", tokens=base + ["carefully", "reviewed", "senior", "linguists", "twice"], keys=["n1.example.com/z", "n2.example.org/z"])
        self.assertEqual(rec["reason"], "DUPLICATE_WORK")

    def test_tiny_token_sets_only_match_exactly(self):
        self.record("PASS", tokens=["deploy", "api"])
        self.assertEqual(self.record("PASS", tokens=["deploy", "web"])["delta"], 10)

    def test_different_work_is_credited(self):
        self.record("PASS", tokens=["translate", "report", "french"])
        rec = self.record("PASS", tokens=["compile", "firmware", "board"])
        self.assertEqual(rec["delta"], 10)

    def test_recycled_evidence_earns_nothing(self):
        self.record("PASS", tokens=["alpha", "beta", "gamma"], keys=["k1.example.com/a", "k2.example.org/b"])
        rec = self.record("PASS", tokens=["delta", "omega", "sigma"], keys=["k1.example.com/a", "k2.example.org/b"])
        self.assertEqual(rec["reason"], "DUPLICATE_WORK")

    def test_one_fresh_source_is_not_enough(self):
        self.record("PASS", tokens=["alpha", "beta", "gamma"], keys=["k1.example.com/a", "k2.example.org/b"])
        rec = self.record("PASS", tokens=["delta", "omega", "sigma"], keys=["k1.example.com/a", "new.example.net/c"])
        self.assertEqual(rec["reason"], "DUPLICATE_WORK")

    def test_two_fresh_sources_are_enough(self):
        self.record("PASS", tokens=["alpha", "beta", "gamma"], keys=["k1.example.com/a", "k2.example.org/b"])
        rec = self.record("PASS", tokens=["delta", "omega", "sigma"], keys=["k1.example.com/a", "new1.example.net/c", "new2.example.io/d"])
        self.assertEqual(rec["delta"], 10)

    def test_legitimate_repeat_after_window_is_credited(self):
        tokens = ["translate", "report", "french", "publish"]
        self.record("PASS", tokens=tokens)
        Clock.now += 8 * DAY
        rec = self.record("PASS", tokens=tokens, keys=["n1.example.com/z", "n2.example.org/z"])
        self.assertEqual((rec["delta"], rec["reason"]), (2, "REPEAT_WORK"))

    def test_repeating_the_same_task_forever_earns_only_the_decayed_rate(self):
        tokens = ["translate", "report", "french", "publish"]
        self.record("PASS", tokens=tokens)
        for week in range(1, 6):
            Clock.now += 8 * DAY
            rec = self.record("PASS", tokens=tokens, keys=["w%da.example.com/z" % week, "w%db.example.org/z" % week])
            self.assertEqual((rec["delta"], rec["reason"]), (2, "REPEAT_WORK"))
        self.assertEqual(self.agent()["score"], 500 + 10 + 5 * 2)

    def test_unrelated_work_after_the_window_still_earns_full_credit(self):
        self.record("PASS", tokens=["translate", "report", "french", "publish"])
        Clock.now += 8 * DAY
        self.assertEqual(self.record("PASS", tokens=["compile", "firmware", "board"])["delta"], 10)

    def test_duplicate_work_still_counts_as_a_pass_but_not_credit(self):
        tokens = ["translate", "report", "french", "publish"]
        self.record("PASS", tokens=tokens)
        self.record("PASS", tokens=tokens, keys=["n1.example.com/z", "n2.example.org/z"])
        a = self.agent()
        self.assertEqual((a["passes"], a["credited"], a["score"]), (2, 1, 510))

    def test_failures_are_never_discounted_as_duplicates(self):
        tokens = ["translate", "report", "french", "publish"]
        self.record("FAIL", tokens=tokens)
        self.assertEqual(self.record("FAIL", tokens=tokens)["delta"], -30)

    def test_failed_attempts_do_not_block_later_credit(self):
        tokens = ["translate", "report", "french", "publish"]
        self.record("FAIL", tokens=tokens)
        self.assertEqual(self.record("PASS", tokens=tokens)["delta"], 10)

    def test_daily_gain_cap(self):
        for _ in range(3):
            self.assertEqual(self.record("PASS")["delta"], 10)
        rec = self.record("PASS")
        self.assertEqual((rec["delta"], rec["reason"]), (0, "DAILY_CAP"))
        Clock.now += DAY
        self.assertEqual(self.record("PASS")["delta"], 10)

    def test_exact_repeat_is_remembered_beyond_the_work_archive(self):
        tokens = ["translate", "report", "french", "publish"]
        self.record("PASS", tokens=tokens)
        for i in range(registry_mod.MAX_RECENT_WORK + 3):
            Clock.now += DAY
            self.record("PASS", tokens=["alpha%d" % i, "beta%d" % i, "gamma%d" % i])
        stored = json.loads(RT.contracts[self.reg].agents[AGENT])
        self.assertNotIn(sorted(tokens), [sorted(w["t"]) for w in stored["work"]])
        Clock.now += 8 * DAY
        rec = self.record("PASS", tokens=list(reversed(tokens)), keys=["z1.example.com/q", "z2.example.org/q"])
        self.assertEqual((rec["delta"], rec["reason"]), (2, "REPEAT_WORK"))

    def test_fingerprint_memory_is_bounded(self):
        for i in range(registry_mod.MAX_FINGERPRINTS + 10):
            Clock.now += DAY
            self.record("PASS", tokens=["w%d" % i, "x%d" % i, "y%d" % i])
        stored = json.loads(RT.contracts[self.reg].agents[AGENT])
        self.assertEqual(len(stored["fp"]), registry_mod.MAX_FINGERPRINTS)

    def test_work_archive_is_bounded(self):
        for i in range(registry_mod.MAX_RECENT_WORK + 5):
            self.record("PASS", tokens=["alpha%d" % i, "beta%d" % i, "gamma%d" % i])
            Clock.now += DAY
        stored = json.loads(RT.contracts[self.reg].agents[AGENT])
        self.assertEqual(len(stored["work"]), registry_mod.MAX_RECENT_WORK)

    def test_agents_are_scored_independently(self):
        tokens = ["translate", "report", "french", "publish"]
        self.record("PASS", agent=AGENT, tokens=tokens)
        self.assertEqual(self.record("PASS", agent=AGENT2, tokens=tokens)["delta"], 10)


class RegistryAccess(RegistryBase):
    def test_only_wired_verifier_may_record(self):
        for sender in (OWNER, AGENT, STRANGER, self.s.vf):
            self.assertRevert(
                lambda who=sender: self.s.call(who, self.reg, "record_result", "9", AGENT, "PASS", "[]", "[]"),
                "only the wired SkillVerifier",
            )
        self.assertEqual(self.agent()["score"], 500)

    def test_unwired_registry_rejects_everyone(self):
        fresh = RT.deploy(registry_mod.ScoreRegistry, (), OWNER)
        self.assertRevert(lambda: self.s.call(OWNER, fresh, "record_result", "1", AGENT, "PASS", "[]", "[]"), "only the wired")

    def test_claim_cannot_be_recorded_twice(self):
        self.record("PASS", claim_id="55")
        self.assertRevert(
            lambda: self.s.call(FAKE_VERIFIER, self.reg, "record_result", "55", AGENT, "PASS", "[]", "[]"),
            "already recorded",
        )
        self.assertEqual(self.agent()["total"], 1)

    def test_invalid_inputs_are_rejected(self):
        call = lambda *a: self.s.call(FAKE_VERIFIER, self.reg, "record_result", *a)
        self.assertRevert(lambda: call("1", AGENT, "MAYBE", "[]", "[]"), "invalid verdict")
        self.assertRevert(lambda: call("1", "nope", "PASS", "[]", "[]"), "invalid address")
        self.assertRevert(lambda: call("1", AGENT, "PASS", "not json", "[]"), "JSON")
        self.assertRevert(lambda: call("1", AGENT, "PASS", json.dumps(["t"] * 129), "[]"), "invalid")
        self.assertRevert(lambda: call("1", AGENT, "PASS", "[]", json.dumps(["k"] * 6)), "invalid")
        self.assertRevert(lambda: call("1", AGENT, "PASS", "[]", json.dumps(["k" * 400])), "invalid")
        self.assertRevert(lambda: call("1", AGENT, "PASS", '{"a": 1}', "[]"), "invalid")

    def test_wiring_is_owner_only_and_one_time(self):
        fresh = RT.deploy(registry_mod.ScoreRegistry, (), OWNER)
        self.assertRevert(lambda: self.s.call(STRANGER, fresh, "set_verifier", FAKE_VERIFIER), "only the owner")
        self.s.call(OWNER, fresh, "set_verifier", FAKE_VERIFIER)
        self.assertRevert(lambda: self.s.call(OWNER, fresh, "set_verifier", self.s.vf), "already set")
        self.s.call(OWNER, fresh, "renounce_ownership")
        self.assertRevert(lambda: self.s.call(OWNER, fresh, "renounce_ownership"), "only the owner")


class RegistryViews(RegistryBase):
    def test_history_and_records_are_kept(self):
        for _ in range(3):
            self.record("PASS")
        a = self.agent()
        self.assertEqual(a["history"], ["1", "2", "3"])
        rec = json.loads(self.s.view(self.reg, "get_record", "2"))
        self.assertEqual((rec["agent"], rec["verdict"], rec["score_before"], rec["score_after"]), (AGENT, "PASS", 510, 520))
        self.assertEqual(self.s.view(self.reg, "get_record", "404"), "")

    def test_history_is_bounded(self):
        for i in range(registry_mod.HISTORY_CAP + 5):
            self.record("INSUFFICIENT_EVIDENCE")
        self.assertEqual(len(self.agent()["history"]), registry_mod.HISTORY_CAP)

    def test_top_agents_sorted_by_score(self):
        self.record("PASS", agent=AGENT)
        self.record("FAIL", agent=AGENT2)
        self.record("PASS", agent=STRANGER)
        self.record("PASS", agent=STRANGER)
        top = json.loads(self.s.view(self.reg, "get_top_agents", 10))
        self.assertEqual([t["agent"] for t in top], [STRANGER, AGENT, AGENT2])
        self.assertEqual(len(json.loads(self.s.view(self.reg, "get_top_agents", 1))), 1)

    def test_recent_is_newest_first_and_bounded(self):
        for _ in range(5):
            self.record("PASS")
        recent = json.loads(self.s.view(self.reg, "list_recent", 3))
        self.assertEqual([r["claim_id"] for r in recent], ["5", "4", "3"])

    def test_list_agents_pagination(self):
        self.record("PASS", agent=AGENT)
        self.record("PASS", agent=AGENT2)
        page = json.loads(self.s.view(self.reg, "list_agents", 1, 10))
        self.assertEqual([p["agent"] for p in page], [AGENT2])
        self.assertRevert(lambda: self.s.view(self.reg, "list_agents", -1, 5), "non-negative")

    def test_agent_lookup_rejects_garbage(self):
        self.assertRevert(lambda: self.s.view(self.reg, "get_agent", "not-an-address"), "invalid address")

    def test_public_agent_view_hides_internal_work_log(self):
        self.record("PASS")
        self.assertNotIn("work", self.agent())


if __name__ == "__main__":
    unittest.main()
