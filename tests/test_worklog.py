import json
import unittest

from harness import (
    RT,
    AGENT,
    AGENT2,
    CLAIM_BOND,
    EXPECTED,
    OWNER,
    STRANGER,
    TASK,
    URL_A,
    URL_B,
    URL_C,
    Base,
    sources_json,
    worklog_mod,
)


class WorkLogSubmission(Base):
    def test_valid_claim_is_stored_immutably(self):
        cid = self.s.submit()
        self.assertEqual(cid, "1")
        claim = self.s.jview(self.s.wl, "get_claim", cid)
        self.assertEqual(claim["agent"], AGENT)
        self.assertEqual(claim["task"], TASK)
        self.assertEqual(claim["expected_result"], EXPECTED)
        self.assertEqual(claim["status"], "SUBMITTED")
        self.assertEqual(claim["verdict"], "")
        self.assertEqual([s["url"] for s in claim["sources"]], [URL_A, URL_B])
        self.assertEqual(self.s.view(self.s.wl, "get_total_claims"), 1)

    def test_agent_identity_is_the_sender(self):
        self.s.fund_agent(AGENT2)
        self.s.advance(61)
        cid = self.s.call(AGENT2, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(URL_A, URL_B))
        self.assertEqual(self.s.jview(self.s.wl, "get_claim", cid)["agent"], AGENT2)

    def test_bond_is_locked_from_deposit(self):
        self.s.fund_agent(AGENT, 3 * CLAIM_BOND)
        self.s.advance(61)
        self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(URL_A, URL_B))
        self.assertEqual(self.s.view(self.s.wl, "get_deposit", AGENT), 2 * CLAIM_BOND)

    def test_submission_requires_deposit(self):
        self.assertRevert(
            lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(URL_A, URL_B)),
            "insufficient deposit",
        )

    def test_invalid_task_and_expected(self):
        self.s.fund_agent()
        self.s.advance(61)
        src = sources_json(URL_A, URL_B)
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", "short", EXPECTED, src), "task")
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, "tiny", src), "expected_result")
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK + "\x00", EXPECTED, src), "control")
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", 5, EXPECTED, src), "string")

    def test_excessive_input_is_rejected(self):
        self.s.fund_agent()
        self.s.advance(61)
        src = sources_json(URL_A, URL_B)
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", "x" * 5000, EXPECTED, src))
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, "y" * 501, src), "expected_result")
        huge = json.dumps(["https://a%d.example.com/" % i for i in range(400)])
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, huge), "too large")
        long_url = "https://alpha.example.com/" + "p" * 400
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(long_url, URL_B)), "url length")

    def test_source_count_bounds(self):
        self.s.fund_agent()
        self.s.advance(61)
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, "[]"), "sources")
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(URL_A)), "sources")
        six = [f"https://site{i}.example.com/x" for i in range(6)]
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(*six)), "sources")
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, "not json"), "JSON")
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, '{"a": 1}'), "JSON")
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, "[1, 2]"), "string")

    def test_duplicate_claim_is_rejected_even_when_reordered(self):
        self.s.submit()
        self.s.fund_agent()
        self.s.advance(61)
        self.assertRevert(
            lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(URL_B, URL_A)),
            "duplicate claim",
        )

    def test_cancelled_claim_can_be_resubmitted(self):
        cid = self.s.submit()
        self.s.call(AGENT, self.s.wl, "cancel_claim", cid)
        self.s.advance(61)
        again = self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(URL_A, URL_B))
        self.assertEqual(again, "2")

    def test_cooldown_between_submissions(self):
        self.s.fund_agent()
        self.s.advance(61)
        self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(URL_A, URL_B))
        self.assertRevert(
            lambda: self.s.call(
                AGENT, self.s.wl, "submit_claim", "Completely different work about pump firmware", EXPECTED, sources_json(URL_C, "https://delta.example.io/x")
            ),
            "cooldown",
        )

    def test_open_claim_cap(self):
        tasks = [
            "Compile the firmware for the pump controller board",
            "Summarise the legal contract for the vendor review",
            "Migrate the customer database to the new schema",
            "Generate the monthly accounting statements pack",
        ]
        for i, task in enumerate(tasks[:3]):
            self.s.submit(task=task, urls=(f"https://one{i}.example.com/a", f"https://two{i}.example.org/b"))
        self.assertRevert(
            lambda: self.s.submit(task=tasks[3], urls=("https://one9.example.com/a", "https://two9.example.org/b")),
            "too many open claims",
        )

    def test_near_duplicate_open_claim_is_rejected(self):
        self.s.submit()
        near = TASK + " today"
        self.assertRevert(
            lambda: self.s.submit(task=near, urls=("https://other1.example.com/a", "https://other2.example.org/b")),
            "similar claim",
        )

    def test_unrelated_open_claim_is_allowed(self):
        self.s.submit()
        cid = self.s.submit(
            task="Compile the firmware for the pump controller board",
            urls=("https://other1.example.com/a", "https://other2.example.org/b"),
        )
        self.assertEqual(cid, "2")


class WorkLogUrls(Base):
    def reject(self, url, fragment=None):
        self.assertRevert(lambda: worklog_mod.normalize_url(url), fragment)

    def test_normalization(self):
        item = worklog_mod.normalize_url("HTTPS://WWW.Example.COM:443/Path//to/doc/#frag")
        self.assertEqual(item["url"], "https://www.example.com/Path//to/doc/")
        self.assertEqual(item["domain"], "example.com")
        self.assertEqual(item["key"], "example.com/path/to/doc")

    def test_fetched_url_keeps_the_original_path(self):
        item = worklog_mod.normalize_url("https://example.com/dir/")
        self.assertEqual(item["url"], "https://example.com/dir/")
        self.assertEqual(worklog_mod.normalize_url("https://example.com/dir")["key"], item["key"])

    def test_trailing_slash_variants_are_one_source(self):
        self.s.fund_agent()
        self.s.advance(61)
        self.assertRevert(
            lambda: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json("https://a.example.com/x/", "https://www.a.example.com/x")),
            "distinct registrable domains",
        )

    def test_agent_history_is_bounded(self):
        self.s.fund_agent(AGENT, 1000 * CLAIM_BOND)
        for i in range(worklog_mod.MAX_HISTORY + 3):
            self.s.advance(61)
            cid = self.s.call(
                AGENT, self.s.wl, "submit_claim", "Unique task number %d about topic%d zebra%d" % (i, i * 7, i * 13), EXPECTED,
                sources_json("https://h%da.example.com/x" % i, "https://h%db.example.org/y" % i),
            )
            self.s.call(AGENT, self.s.wl, "cancel_claim", cid)
        ids = json.loads(self.s.view(self.s.wl, "get_agent_claim_ids", AGENT))
        self.assertEqual(len(ids), worklog_mod.MAX_HISTORY)
        self.assertEqual(ids[-1], str(worklog_mod.MAX_HISTORY + 3))

    def test_freshness_key_ignores_subdomains(self):
        a = worklog_mod.normalize_url("https://alpha.example.com/report")["key"]
        b = worklog_mod.normalize_url("https://beta.example.com/report")["key"]
        self.assertEqual((a, b), ("example.com/report", "example.com/report"))
        self.assertEqual(worklog_mod.normalize_url("https://a.github.io/x")["key"], "github.com/x")

    def test_stopwords_are_not_tokens(self):
        self.assertEqual(worklog_mod.tokens_of("The report and the summary for the team"), ["report", "summary", "team"])

    def test_punycode_tld_is_accepted(self):
        self.assertEqual(worklog_mod.normalize_url("https://example.xn--p1ai/a")["domain"], "example.xn--p1ai")

    def test_query_kept_in_url_but_not_in_key(self):
        a = worklog_mod.normalize_url("https://example.com/r?id=1")
        b = worklog_mod.normalize_url("https://example.com/r?id=2")
        self.assertNotEqual(a["url"], b["url"])
        self.assertEqual(a["key"], b["key"])

    def test_rejected_urls(self):
        self.reject("http://example.com/a", "https")
        self.reject("ftp://example.com/a", "https")
        self.reject("javascript:alert(1)", "https")
        self.reject("https://user:pw@example.com/a", "credentials")
        self.reject("https://example.com:443@attacker.example/", "credentials")
        self.reject("https://example.com:8443/a", "port")
        self.reject("https://localhost/a", "host")
        self.reject("https://127.0.0.1/a", "host")
        self.reject("https://10.0.0.1/a", "host")
        self.reject("https://0x7f.1/a", "host")
        self.reject("https://example.123/a", "host")
        self.reject("https://printer.local/a", "private")
        self.reject("https://intranet/a", "host")
        self.reject("https://exa mple.com/a", "ascii")
        self.reject("https://example.com/é", "ascii")
        self.reject("", "length")
        self.reject("https://[::1]/a", "host")
        self.reject(None, "string")

    def test_same_domain_sources_are_rejected(self):
        self.s.fund_agent()
        self.s.advance(61)
        for pair in (
            ("https://example.com/a", "https://example.com/b"),
            ("https://example.com/a", "https://docs.example.com/b"),
            ("https://www.example.com/a", "https://example.com/a"),
            ("https://github.com/o/r", "https://raw.githubusercontent.com/o/r/main/x"),
        ):
            self.assertRevert(
                lambda p=pair: self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(*p)),
                "distinct registrable domains",
            )

    def test_registrable_domain_rules(self):
        d = worklog_mod.registrable_domain
        self.assertEqual(d("a.b.example.com"), "example.com")
        self.assertEqual(d("shop.example.co.uk"), "example.co.uk")
        self.assertEqual(d("alice.github.io"), "github.com")
        self.assertEqual(d("alice.github.io"), d("bob.github.io"))
        self.assertEqual(d("raw.githubusercontent.com"), "github.com")
        self.assertEqual(d("a.netlify.app"), d("b.netlify.app"))
        self.assertEqual(d("localhost"), "")


class WorkLogAccess(Base):
    def test_only_claim_agent_can_cancel_or_request(self):
        cid = self.s.submit()
        self.assertRevert(lambda: self.s.call(STRANGER, self.s.wl, "cancel_claim", cid), "only the claim agent")
        self.assertRevert(lambda: self.s.call(STRANGER, self.s.wl, "request_verification", cid), "only the claim agent")

    def test_close_and_mark_methods_are_verifier_only(self):
        cid = self.s.submit()
        self.s.start(cid)
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "close_claim", cid, "PASS"), "wired verifier")
        self.assertRevert(lambda: self.s.call(OWNER, self.s.wl, "close_claim", cid, "PASS"), "wired verifier")

    def test_no_method_edits_claim_metadata(self):
        public = [n for n in dir(worklog_mod.WorkLog) if getattr(getattr(worklog_mod.WorkLog, n), "_gl_kind", None) in ("write", "payable")]
        self.assertEqual(
            sorted(public),
            sorted(["set_verifier", "renounce_ownership", "deposit", "withdraw", "submit_claim", "cancel_claim", "request_verification", "retry_open_job", "close_claim"]),
        )

    def test_verifier_wiring_is_owner_only_and_one_time(self):
        fresh = RT.deploy(worklog_mod.WorkLog, (), OWNER)
        self.assertRevert(lambda: self.s.call(STRANGER, fresh, "set_verifier", self.s.vf), "only the owner")
        self.s.call(OWNER, fresh, "set_verifier", self.s.vf)
        self.assertRevert(lambda: self.s.call(OWNER, fresh, "set_verifier", self.s.sr), "already set")

    def test_renounce_removes_owner_powers(self):
        fresh = RT.deploy(worklog_mod.WorkLog, (), OWNER)
        self.s.call(OWNER, fresh, "renounce_ownership")
        self.assertRevert(lambda: self.s.call(OWNER, fresh, "set_verifier", self.s.vf), "only the owner")

    def test_state_transitions(self):
        cid = self.s.submit()
        self.s.start(cid)
        self.assertRevert(lambda: self.s.start(cid), "SUBMITTED")
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "cancel_claim", cid), "SUBMITTED")
        self.assertEqual(self.s.jview(self.s.wl, "get_claim", cid)["status"], "VERIFYING")
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "cancel_claim", "99"), "not found")


class WorkLogDeposits(Base):
    def test_withdraw_returns_free_balance_once(self):
        self.s.fund_agent(AGENT, 5 * CLAIM_BOND)
        before = RT.balances.get(AGENT, 0)
        paid = self.s.call(AGENT, self.s.wl, "withdraw")
        self.assertEqual(paid, 5 * CLAIM_BOND)
        self.assertEqual(RT.balances[AGENT] - before, 5 * CLAIM_BOND)
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "withdraw"), "nothing to withdraw")

    def test_zero_deposit_is_rejected(self):
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "deposit", value=0), "positive")

    def test_cannot_withdraw_someone_elses_balance(self):
        self.s.fund_agent(AGENT, 5 * CLAIM_BOND)
        self.assertRevert(lambda: self.s.call(STRANGER, self.s.wl, "withdraw"), "nothing to withdraw")

    def test_locked_bond_cannot_be_withdrawn(self):
        self.s.fund_agent(AGENT, CLAIM_BOND)
        self.s.advance(61)
        self.s.call(AGENT, self.s.wl, "submit_claim", TASK, EXPECTED, sources_json(URL_A, URL_B))
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "withdraw"), "nothing to withdraw")

    def test_cancel_returns_bond_to_deposit(self):
        cid = self.s.submit()
        before = self.s.view(self.s.wl, "get_deposit", AGENT)
        self.s.call(AGENT, self.s.wl, "cancel_claim", cid)
        self.assertEqual(self.s.view(self.s.wl, "get_deposit", AGENT), before + CLAIM_BOND)
        self.assertRevert(lambda: self.s.call(AGENT, self.s.wl, "cancel_claim", cid), "SUBMITTED")

    def test_balance_covers_deposits_and_locked_bonds(self):
        self.s.submit()
        cfg = self.s.jview(self.s.wl, "get_config")
        free = self.s.view(self.s.wl, "get_deposit", AGENT)
        self.assertEqual(self.s.contract_balance(self.s.wl), free + cfg["locked_total"])


if __name__ == "__main__":
    unittest.main()
