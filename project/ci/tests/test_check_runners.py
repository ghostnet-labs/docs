"""Regression tests for project/scripts/check_runners.py.

Kept out of project/tests on purpose: the merge gate runs that suite with
the runner's bare python3, which has no PyYAML.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "project" / "scripts"))

import yaml  # noqa: E402

import check_runners as cr  # noqa: E402

FORK_FALLBACK = ("${{ (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) "
                 "&& fromJSON('[\"self-hosted\", \"macOS\", \"ARM64\"]') || 'ubuntu-latest' }}")


def wf(text):
    return yaml.safe_load(text)


def rules(findings):
    return sorted((f.job, f.rule) for f in findings)


class RuleTest(unittest.TestCase):
    def test_clean_self_hosted_pr_workflow(self):
        doc = wf("""
on: pull_request
concurrency: {group: x, cancel-in-progress: true}
jobs:
  t:
    runs-on: ${{ (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) && fromJSON('["self-hosted", "Linux", "ARM64"]') || 'ubuntu-latest' }}
    timeout-minutes: 10
    steps: []
""")
        self.assertEqual(cr.check_workflow("r", "w.yml", doc), [])

    def test_self_hosted_pr_job_without_fork_guard(self):
        doc = wf("""
on: [pull_request]
concurrency: {group: x, cancel-in-progress: true}
jobs:
  t: {runs-on: [self-hosted, Linux, ARM64], timeout-minutes: 10, steps: []}
  u: {runs-on: ubuntu-latest, timeout-minutes: 10, steps: []}
""")
        found = cr.check_workflow("r", "w.yml", doc)
        self.assertEqual([(f.job, f.rule) for f in found if f.rule == "fork-pr-self-hosted"],
                         [("t", "fork-pr-self-hosted")])

    def test_self_hosted_job_without_pr_trigger_needs_no_guard(self):
        doc = wf("""
on: {push: {branches: [main]}, schedule: [{cron: '41 * * * *'}]}
jobs:
  t: {runs-on: [self-hosted, Linux, ARM64], timeout-minutes: 10, steps: []}
""")
        self.assertEqual(cr.check_workflow("r", "w.yml", doc), [])

    def test_fork_guard_must_compare_head_repo(self):
        self.assertTrue(cr.has_fork_guard(
            "${{ github.repository == github.event.pull_request.head.repo.full_name && fromJSON('[\"self-hosted\"]') || 'ubuntu-latest' }}"))
        self.assertFalse(cr.has_fork_guard("${{ github.actor == 'x' && fromJSON('[\"self-hosted\"]') || 'ubuntu-latest' }}"))
        self.assertFalse(cr.has_fork_guard(["self-hosted", "Linux"]))

    def test_fork_fallback_expression_counts_as_self_hosted(self):
        self.assertTrue(cr.is_self_hosted(FORK_FALLBACK))
        self.assertFalse(cr.is_self_hosted("ubuntu-latest"))
        self.assertFalse(cr.is_self_hosted(["ubuntu-24.04"]))

    def test_hosted_job_without_timeout_or_cancel(self):
        doc = wf("""
on: [pull_request, push]
jobs:
  b: {runs-on: ubuntu-latest, steps: []}
""")
        self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)),
                         [("b", "hosted-runner"), ("b", "job-timeout"), ("b", "pr-concurrency")])

    def test_cancel_in_progress_expression_and_job_level(self):
        doc = wf("""
on: {pull_request: {}, push: {}}
concurrency:
  group: g
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
jobs:
  a: {runs-on: "${{ github.event.pull_request.head.repo.full_name == github.repository && 'self-hosted' || 'ubuntu-latest' }}", timeout-minutes: 5, steps: []}
""")
        self.assertEqual(cr.check_workflow("r", "w.yml", doc), [])
        doc = wf("""
on: pull_request
concurrency: {group: g, cancel-in-progress: false}
jobs:
  a: {runs-on: "${{ github.event.pull_request.head.repo.full_name == github.repository && 'self-hosted' || 'ubuntu-latest' }}", timeout-minutes: 5, concurrency: {group: j, cancel-in-progress: true}, steps: []}
  b: {runs-on: "${{ github.event.pull_request.head.repo.full_name == github.repository && 'self-hosted' || 'ubuntu-latest' }}", timeout-minutes: 5, steps: []}
""")
        self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)), [("b", "pr-concurrency")])

    def test_push_only_workflow_needs_no_cancel(self):
        doc = wf("""
on: {push: {branches: [main]}}
jobs:
  a: {runs-on: [self-hosted], timeout-minutes: 5, steps: []}
""")
        self.assertEqual(cr.check_workflow("r", "w.yml", doc), [])

    def test_subhourly_cron_only_flagged_on_hosted(self):
        cron = "on: {schedule: [{cron: '3,18,33,48 * * * *'}]}\n"
        hosted = wf(cron + "jobs: {a: {runs-on: ubuntu-latest, timeout-minutes: 5, steps: []}}")
        mac = wf(cron + "jobs: {a: {runs-on: [self-hosted], timeout-minutes: 5, steps: []}}")
        self.assertIn(("a", "hosted-cron"), rules(cr.check_workflow("r", "w.yml", hosted)))
        self.assertEqual(cr.check_workflow("r", "w.yml", mac), [])

    def test_cron_minute_field(self):
        for expr, sub in [("*/15 * * * *", True), ("* * * * *", True), ("0-30 * * * *", True),
                          ("3,33 * * * *", True), ("41 * * * *", False), ("0 3 * * 1", False),
                          ("*/60 * * * *", False)]:
            with self.subTest(expr=expr):
                self.assertEqual(cr.cron_is_subhourly(expr), sub)

    def test_reusable_workflows(self):
        doc = wf("""
on: workflow_dispatch
jobs:
  local: {uses: ./.github/workflows/build.yml}
  pinned: {uses: org/repo/.github/workflows/k.yml@0123456789abcdef0123456789abcdef01234567}
  branch: {uses: org/repo/.github/workflows/k.yml@main}
""")
        self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)), [("branch", "pinned-reusable")])

    def test_remote_reusable_on_schedule_counts_as_hosted(self):
        doc = wf("""
on: {schedule: [{cron: '*/5 * * * *'}]}
jobs:
  k: {uses: org/repo/.github/workflows/k.yml@0123456789abcdef0123456789abcdef01234567}
""")
        self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)), [("k", "hosted-cron")])


class AllowlistTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp))

    def write(self, entries):
        p = self.tmp / "allow.json"
        p.write_text(json.dumps({"entries": entries}))
        return p

    def test_allowlist_needs_reason_and_known_rules(self):
        base = {"repo": "r", "workflow": "w.yml", "job": "*", "rules": ["hosted-runner"], "reason": "why"}
        cr.load_allowlist(self.write([base]))
        with self.assertRaises(ValueError):
            cr.load_allowlist(self.write([{**base, "reason": " "}]))
        with self.assertRaises(ValueError):
            cr.load_allowlist(self.write([{**base, "rules": ["no-such-rule"]}]))
        with self.assertRaises(ValueError):
            cr.load_allowlist(self.write([{k: v for k, v in base.items() if k != "reason"}]))

    def test_allowlist_waives_only_named_rules_and_reports_unused(self):
        f1 = cr.Finding("r", "w.yml", "a", "hosted-runner", "")
        f2 = cr.Finding("r", "w.yml", "a", "job-timeout", "")
        entries = [
            {"repo": "r", "workflow": "w*.yml", "job": "*", "rules": ["hosted-runner"], "reason": "x"},
            {"repo": "r", "workflow": "gone.yml", "job": "*", "rules": ["job-timeout"], "reason": "x"},
            {"repo": "other", "workflow": "*", "job": "*", "rules": ["job-timeout"], "reason": "x"},
        ]
        violations, allowed, unused = cr.apply_allowlist([f1, f2], entries, ["r"])
        self.assertEqual(violations, [f2])
        self.assertEqual(allowed, [f1])
        self.assertEqual([e["workflow"] for e in unused], ["gone.yml"])

    def test_main_exit_codes(self):
        wfdir = self.tmp / "wf"
        wfdir.mkdir()
        (wfdir / "ci.yml").write_text("on: pull_request\njobs:\n  a: {runs-on: ubuntu-latest, steps: []}\n")
        allow = self.write([])
        self.assertEqual(cr.main(["--repo", "r", "--workflows", str(wfdir), "--allowlist", str(allow)]), 1)
        allow = self.write([{"repo": "r", "workflow": "ci.yml", "job": "a",
                             "rules": ["hosted-runner", "job-timeout", "pr-concurrency"], "reason": "x"}])
        self.assertEqual(cr.main(["--repo", "r", "--workflows", str(wfdir), "--allowlist", str(allow)]), 0)


class RepositoryAllowlistTest(unittest.TestCase):
    def test_checked_in_allowlist_is_valid(self):
        entries = cr.load_allowlist(cr.DEFAULT_ALLOWLIST)
        self.assertTrue(entries)

    def test_docs_workflows_pass(self):
        entries = cr.load_allowlist(cr.DEFAULT_ALLOWLIST)
        found = cr.check_repo("docs", ROOT / ".github" / "workflows")
        violations, _, _ = cr.apply_allowlist(found, entries, ["docs"])
        self.assertEqual(violations, [], "\n".join(map(str, violations)))


if __name__ == "__main__":
    unittest.main()
