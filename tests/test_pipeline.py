import unittest
from harness.pipeline import Ticket, ChangeSet, run, stub_agent

T = Ticket("T-1", "Doc export", "", ["Explains flags"])

class PipelineTest(unittest.TestCase):
    def test_releases_when_gates_pass_and_reviewer_approves(self):
        self.assertEqual(run(T, stub_agent, reviewer=lambda s, c: True).stage, "release")

    def test_waits_for_human_review_by_default(self):
        self.assertEqual(run(T, stub_agent).stage, "awaiting-review")

    def test_rejects_ticket_without_acceptance(self):
        self.assertEqual(run(Ticket("T-2", "x", "", []), stub_agent).stage, "rejected")

    def test_blocks_failing_tests(self):
        rec = run(T, lambda s: ChangeSet({"a.py": "x"}, tests_passed=False), reviewer=lambda s, c: True)
        self.assertEqual(rec.stage, "blocked")
        self.assertIn("tests", rec.events[-1]["failed"])

    def test_blocks_secret(self):
        rec = run(T, lambda s: ChangeSet({"c.env": "password=hunter2"}, True), reviewer=lambda s, c: True)
        self.assertIn("no-secrets", rec.events[-1]["failed"])

if __name__ == "__main__":
    unittest.main()
