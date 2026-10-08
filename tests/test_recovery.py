import json

from harness import AGENT, RT, STRANGER, URL_A, URL_B, WINDOW, Base, good


class DroppedOpenJob(Base):
    def setUp(self):
        super().setUp()
        RT.pages = {URL_A: good(URL_A), URL_B: good(URL_B)}
        RT.drop = {"open_job"}
        self.cid = self.s.submit()
        self.s.start(self.cid)

    def test_claim_is_stuck_without_a_job_until_retry(self):
        self.assertEqual(RT.dropped, ["open_job"])
        self.assertRevert(lambda: self.s.evaluate(self.cid), "job not found")

    def test_retry_is_agent_only_and_rate_limited(self):
        RT.drop = set()
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "retry_open_job", self.cid), "not allowed yet")
        self.s.advance(3601)
        self.assertRevert(lambda: self.s.call(STRANGER, self.s.wl, "retry_open_job", self.cid), "only the claim agent")

    def test_retry_recovers_the_claim(self):
        RT.drop = set()
        self.s.advance(3601)
        self.s.call(AGENT, self.s.wl, "retry_open_job", self.cid)
        self.assertEqual(self.s.evaluate(self.cid), "PASS")
        self.assertEqual(self.s.finalize_after_window(self.cid), "PASS")
        self.assertEqual(json.loads(self.s.view(self.s.wl, "get_claim", self.cid))["status"], "FINALIZED")

    def test_retry_is_harmless_when_the_job_already_exists(self):
        RT.drop = set()
        self.s.advance(3601)
        self.s.call(AGENT, self.s.wl, "retry_open_job", self.cid)
        self.s.call(AGENT, self.s.wl, "retry_open_job", self.cid)
        self.assertEqual(self.s.view(self.s.vf, "get_job_count"), 1)

    def test_retry_requires_verifying_state(self):
        cid = self.s.submit(task="Compile the firmware for the pump controller board", urls=("https://x1.example.com/a", "https://x2.example.org/b"))
        self.s.advance(3601)
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "retry_open_job", cid), "VERIFYING")


class DroppedFinalization(Base):
    def setUp(self):
        super().setUp()
        self.cid = self.s.run_to_verified()
        RT.drop = {"close_claim", "record_result"}
        self.s.finalize_after_window(self.cid)

    def test_lost_messages_leave_claim_and_score_untouched(self):
        self.assertEqual(json.loads(self.s.view(self.s.wl, "get_claim", self.cid))["status"], "VERIFYING")
        self.assertEqual(json.loads(self.s.view(self.s.sr, "get_agent", AGENT))["score"], 500)

    def test_resend_repairs_both_contracts(self):
        RT.drop = set()
        self.s.advance(3601)
        self.s.call(STRANGER, self.s.vf, "resend_finalization", self.cid)
        self.assertEqual(json.loads(self.s.view(self.s.wl, "get_claim", self.cid))["status"], "FINALIZED")
        self.assertEqual(json.loads(self.s.view(self.s.sr, "get_agent", AGENT))["score"], 510)

    def test_resend_is_rate_limited_and_capped(self):
        RT.drop = set()
        self.assertRevert(lambda: self.s.call(STRANGER, self.s.vf, "resend_finalization", self.cid), "not allowed yet")
        self.s.advance(3601)
        for _ in range(3):
            self.s.call(STRANGER, self.s.vf, "resend_finalization", self.cid)
        self.assertRevert(lambda: self.s.call(STRANGER, self.s.vf, "resend_finalization", self.cid), "limit")

    def test_resend_is_idempotent(self):
        RT.drop = set()
        self.s.advance(3601)
        for _ in range(3):
            self.s.call(STRANGER, self.s.vf, "resend_finalization", self.cid)
        self.assertEqual(json.loads(self.s.view(self.s.sr, "get_agent", AGENT))["score"], 510)
        self.assertEqual(json.loads(self.s.view(self.s.sr, "get_stats"))["total"], 1)
        self.assertEqual(self.s.view(self.s.wl, "get_deposit", AGENT), 10 * 10**16)

    def test_resend_requires_a_finalized_job(self):
        s = type(self.s)()
        cid = s.run_to_verified()
        self.assertRevert(lambda: s.call(STRANGER, s.vf, "resend_finalization", cid), "not finalized")
