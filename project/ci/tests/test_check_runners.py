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

FORK_FALLBACK = ("${{ github.event.pull_request.head.repo.full_name == github.repository && "
                 "fromJSON('[\"self-hosted\", \"macOS\", \"ARM64\"]') || 'ubuntu-24.04' }}")


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
    runs-on: ${{ (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) && fromJSON('["self-hosted", "Linux", "ARM64"]') || 'ubuntu-24.04' }}
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
  u: {runs-on: ubuntu-24.04, timeout-minutes: 10, steps: []}
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

    def test_fork_guard_accepts_only_exact_forms(self):
        head = "github.event.pull_request.head.repo.full_name == github.repository"
        pick = "fromJSON('[\"self-hosted\"]')"
        ok = [
            f"${{{{ {head} && {pick} || 'ubuntu-24.04' }}}}",
            f"${{{{ github.repository == github.event.pull_request.head.repo.full_name && {pick} || 'ubuntu-24.04' }}}}",
            f"${{{{ (github.event_name != 'pull_request' || {head}) && {pick} || 'ubuntu-24.04' }}}}",
            cr.ARC_FORK_FALLBACK,
        ]
        pr_only = f"${{{{ github.event_name == 'pull_request' && {head} && {pick} || 'ubuntu-24.04' }}}}"
        ok += [pr_only, cr.ARC_PR_ONLY_FALLBACK]
        for text in ok:
            self.assertTrue(cr.has_fork_guard(text), text)
        # the pull-request-only forms never match pull_request_target, so they are
        # fine for workflows that also trigger on it
        self.assertTrue(cr.has_fork_guard(pr_only, allow_event_form=False))
        self.assertTrue(cr.has_fork_guard(cr.ARC_PR_ONLY_FALLBACK, allow_event_form=False))
        self.assertFalse(cr.has_fork_guard(cr.ARC_FORK_FALLBACK, allow_event_form=False))
        bad = [
            ["self-hosted", "Linux"],
            "self-hosted",
            "ghostnet-linux-arm64",
            ["ghostnet-linux-arm64"],
            f"${{{{ github.actor == 'x' && {pick} || 'ubuntu-24.04' }}}}",
            # inverted: forks get the Macs
            f"${{{{ github.event.pull_request.head.repo.full_name != github.repository && {pick} || 'ubuntu-24.04' }}}}",
            # the head check is only one side of an ||, so it never restricts
            f"${{{{ ({head} || github.event_name == 'pull_request') && {pick} || 'ubuntu-24.04' }}}}",
            f"${{{{ {head} || {pick} }}}}",
            f"${{{{ github.event_name != 'pull_request' && {head} && {pick} || 'ubuntu-24.04' }}}}",
            f"${{{{ github.event_name == 'pull_request' && {pick} || 'ubuntu-24.04' }}}}",
            # inverted selector: same-repo PRs get a hosted runner, forks get the Macs
            f"${{{{ {head} && 'ubuntu-24.04' || 'self-hosted' }}}}",
            f"${{{{ {head} && fromJSON('[\"ubuntu-24.04\"]') || 'ubuntu-24.04' }}}}",
            # fallback must be a GitHub-hosted label, never a self-hosted one
            f"${{{{ {head} && {pick} || 'self-hosted' }}}}",
            cr.ARC_FORK_FALLBACK.replace("|| 'ubuntu-24.04'", "|| 'ghostnet-linux-arm64'"),
            cr.ARC_PR_ONLY_FALLBACK.replace("full_name ==", "full_name !="),
            # guard in the fallback position instead of the selector
            f"${{{{ true && {pick} || ({head} && 'a' || 'b') }}}}",
        ]
        for text in bad:
            self.assertFalse(cr.has_fork_guard(text), text)

    def test_event_form_needs_only_safe_triggers(self):
        head = "github.event.pull_request.head.repo.full_name == github.repository"
        event_form = (f"${{{{ (github.event_name != 'pull_request' || {head}) && "
                      "fromJSON('[\"self-hosted\"]') || 'ubuntu-24.04' }}")
        doc = wf("on: [pull_request, workflow_run]\nconcurrency: {group: x, cancel-in-progress: true}\n"
                 "jobs:\n  t:\n    runs-on: \"" + event_form.replace('"', '\\"') + "}\"\n"
                 "    timeout-minutes: 5\n    steps: []\n")
        self.assertIn("fork-pr-self-hosted", [f.rule for f in cr.check_workflow("r", "w.yml", doc)])

    def test_pull_request_target_rejects_event_name_disjunct(self):
        head = "github.event.pull_request.head.repo.full_name == github.repository"
        event_form = (f"${{{{ (github.event_name != 'pull_request' || {head}) && "
                      "fromJSON('[\"self-hosted\"]') || 'ubuntu-24.04' }}")
        plain = f"${{{{ {head} && fromJSON('[\"self-hosted\"]') || 'ubuntu-24.04' }}}}"
        self.assertTrue(cr.has_fork_guard(plain, allow_event_form=False))
        self.assertFalse(cr.has_fork_guard(event_form + "}", allow_event_form=False))
        doc = wf("on: pull_request_target\nconcurrency: {group: x, cancel-in-progress: true}\n"
                 "jobs:\n  t:\n    runs-on: \"" + event_form.replace('"', '\\"') + "}\"\n"
                 "    timeout-minutes: 5\n    steps: []\n")
        self.assertIn("fork-pr-self-hosted", [f.rule for f in cr.check_workflow("r", "w.yml", doc)])

    def test_reusable_workflow_jobs_need_a_fork_guard(self):
        def found(route):
            doc = {"on": {"workflow_call": {}},
                   "jobs": {"build": {"runs-on": route, "timeout-minutes": 10}}}
            return [f.rule for f in cr.check_workflow("r", "w.yml", doc)]
        head = "github.event.pull_request.head.repo.full_name == github.repository"
        event_form = (f"${{{{ (github.event_name != 'pull_request' || {head}) && "
                      "fromJSON('[\"self-hosted\"]') || 'ubuntu-24.04' }}")
        for route in (["self-hosted", "Linux"], "ghostnet-linux-arm64", event_form, cr.ARC_FORK_FALLBACK):
            with self.subTest(route=route):
                self.assertIn("fork-pr-self-hosted", found(route))
        for route in (f"${{{{ {head} && fromJSON('[\"self-hosted\"]') || 'ubuntu-24.04' }}}}",
                      cr.ARC_PR_ONLY_FALLBACK):
            with self.subTest(route=route):
                self.assertNotIn("fork-pr-self-hosted", found(route))

    def test_arc_routes_as_fork_guards_on_pr_workflows(self):
        def found(on, route):
            doc = {"on": on, "concurrency": {"group": "ci", "cancel-in-progress": True},
                   "jobs": {"test": {"runs-on": route, "timeout-minutes": 10}}}
            return rules(cr.check_workflow("r", "w.yml", doc))
        self.assertEqual(found(["pull_request", "push"], cr.ARC_FORK_FALLBACK), [])
        self.assertEqual(found(["pull_request_target", "push"], cr.ARC_PR_ONLY_FALLBACK), [])
        for on in (["pull_request", "workflow_run"], ["pull_request_target"]):
            with self.subTest(on=on):
                self.assertEqual(found(on, cr.ARC_FORK_FALLBACK), [("test", "fork-pr-self-hosted")])

    def test_fork_fallback_expression_counts_as_self_hosted(self):
        self.assertTrue(cr.is_self_hosted(FORK_FALLBACK))
        self.assertFalse(cr.is_self_hosted("ubuntu-24.04"))
        self.assertFalse(cr.is_self_hosted(["ubuntu-24.04"]))

    def test_hosted_job_without_timeout_or_cancel(self):
        doc = wf("""
on: [pull_request, push]
jobs:
  b: {runs-on: ubuntu-24.04, steps: []}
""")
        self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)),
                         [("b", "hosted-runner"), ("b", "job-timeout"), ("b", "pr-concurrency")])

    def test_arc_exact_static_labels_count_as_self_hosted(self):
        for route in ("ghostnet-linux-arm64", ["ghostnet-linux-arm64"],
                      {"labels": "ghostnet-linux-arm64"},
                      {"group": "ci", "labels": ["ghostnet-linux-arm64"]}):
            with self.subTest(route=route):
                doc = {"on": "push", "jobs": {"test": {"runs-on": route, "timeout-minutes": 10}}}
                self.assertEqual(cr.check_workflow("r", "w.yml", doc), [])
                # A static ARC label lets fork PR code onto the cluster.
                doc = {"on": "pull_request",
                       "concurrency": {"group": "ci", "cancel-in-progress": True},
                       "jobs": {"test": {"runs-on": route, "timeout-minutes": 10}}}
                self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)),
                                 [("test", "fork-pr-self-hosted")])

    def test_arc_substrings_and_non_label_fields_do_not_waive_policy(self):
        for route in ("ghostnet-linux-arm64-spoof", "prefix-ghostnet-linux-arm64",
                      "ghostnet-linux-arm64 ubuntu-24.04", "GHOSTNET-LINUX-ARM64",
                      ["ghostnet-linux-arm64-spoof"],
                      {"group": "ghostnet-linux-arm64", "labels": "ubuntu-24.04"},
                      {"labels": {"nested": "ghostnet-linux-arm64"}},
                      "${{ inputs.ghostnet-linux-arm64 }}",
                      "${{ contains('ghostnet-linux-arm64', 'arm') && 'ubuntu-24.04' }}",
                      "${{ 'ghostnet-linux-arm64' }}", None):
            with self.subTest(route=route):
                doc = {"on": "push", "jobs": {"test": {"runs-on": route, "timeout-minutes": 10}}}
                self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)),
                                 [("test", "hosted-runner")])

    def test_arc_keeps_other_policy_rules_and_legacy_fallback(self):
        doc = {"on": "pull_request", "jobs": {"test": {"runs-on": "ghostnet-linux-arm64"}}}
        self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)),
                         [("test", "fork-pr-self-hosted"), ("test", "job-timeout"), ("test", "pr-concurrency")])
        self.assertTrue(cr.is_self_hosted(FORK_FALLBACK))
        self.assertTrue(cr.is_self_hosted({"group": "ci", "labels": ["self-hosted", "Linux"]}))

    def test_canonical_arc_fork_fallback_is_recognized(self):
        route = ("${{ (github.event_name != 'pull_request' || "
                 "github.event.pull_request.head.repo.full_name == github.repository) "
                 "&& 'ghostnet-linux-arm64' || 'ubuntu-24.04' }}")
        for value in (route, route.replace(" || ", "\n  ||\t")):
            with self.subTest(route=value):
                doc = {"on": "pull_request", "jobs": {"test": {"runs-on": value}}}
                self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)),
                                 [("test", "job-timeout"), ("test", "pr-concurrency")])

    def test_modified_arc_fork_expressions_are_rejected(self):
        canonical = cr.ARC_FORK_FALLBACK
        for route in (canonical.replace("!= 'pull_request'", "== 'pull_request'"),
                      canonical.replace("full_name ==", "full_name !="),
                      canonical.replace("|| 'ubuntu-24.04'", "|| 'ghostnet-linux-arm64'"),
                      canonical.replace("&& 'ghostnet-linux-arm64'", "&& 'ubuntu-24.04'"),
                      canonical.replace("github.repository", "'attacker/repository'"),
                      canonical.replace("ghostnet-linux-arm64", "ghostnet-linux-arm64-spoof"),
                      canonical.replace("ghostnet-linux-arm64", "ghostnet- linux-arm64"),
                      canonical.replace("|| 'ubuntu-24.04'", "|| 'linux-arm64'"),
                      "${{ inputs.note == 'ghostnet-linux-arm64' && 'ubuntu-24.04' }}"):
            with self.subTest(route=route):
                self.assertFalse(cr.is_self_hosted(route))

    def test_pr_only_arc_route_preserves_hosted_publish_boundary(self):
        route = cr.ARC_PR_ONLY_FALLBACK
        for value in (route, route.replace(" && ", "\n &&\t")):
            with self.subTest(route=value):
                self.assertTrue(cr.is_self_hosted(value))

    def test_pr_only_arc_route_still_checks_hosted_cron(self):
        doc = {"on": {"schedule": [{"cron": "*/15 * * * *"}]},
               "jobs": {"test": {"runs-on": cr.ARC_PR_ONLY_FALLBACK, "timeout-minutes": 10}}}
        self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)),
                         [("test", "hosted-cron")])

    def test_modified_pr_only_arc_routes_are_rejected(self):
        route = cr.ARC_PR_ONLY_FALLBACK
        for value in (route.replace("event_name ==", "event_name !="),
                      route.replace("full_name ==", "full_name !="),
                      route.replace(" && ", " || ", 1),
                      route.replace("pull_request", "pull_request_target"),
                      route.replace("ghostnet-linux-arm64", "ghostnet-linux-arm64-spoof"),
                      route.replace("github.repository", "inputs.repository"),
                      route.replace("ubuntu-24.04", "ghostnet-linux-arm64")):
            with self.subTest(route=value):
                self.assertFalse(cr.is_self_hosted(value))

    def test_large_arc_pool_routes_are_recognized(self):
        large = "ghostnet-linux-arm64-large"
        # The exact route openmanetd's codeql.yml uses for Go CodeQL.
        route = ("${{ (github.event_name != 'pull_request' || "
                 "github.event.pull_request.head.repo.full_name == github.repository) "
                 "&& 'ghostnet-linux-arm64-large' || 'ubuntu-24.04' }}")
        self.assertEqual(route, cr.arc_fork_fallback(large))
        doc = {"on": {"pull_request": {}, "push": {}, "schedule": [{"cron": "34 15 * * 0"}],
                      "workflow_dispatch": {}},
               "concurrency": {"group": "g", "cancel-in-progress": True},
               "jobs": {"analyze": {"runs-on": route, "timeout-minutes": 60}}}
        self.assertEqual(cr.check_workflow("r", "w.yml", doc), [])
        self.assertTrue(cr.has_fork_guard(cr.arc_pr_only_fallback(large), allow_event_form=False))
        self.assertFalse(cr.has_fork_guard(route, allow_event_form=False))
        for static in (large, [large], {"labels": large}):
            with self.subTest(route=static):
                self.assertTrue(cr.is_self_hosted(static))
                # A static large-pool label still lets fork PR code onto the cluster.
                doc = {"on": "pull_request",
                       "concurrency": {"group": "ci", "cancel-in-progress": True},
                       "jobs": {"test": {"runs-on": static, "timeout-minutes": 10}}}
                self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)),
                                 [("test", "fork-pr-self-hosted")])

    def test_gate_pool_same_repo_route_is_recognized(self):
        # The reviewed route for firmware's pr-gate.yml and manet-merge-gate.yml.
        route = cr.arc_pr_only_fallback("ghostnet-gate")
        doc = {"on": {"pull_request": {"types": ["opened", "synchronize"]}},
               "concurrency": {"group": "g", "cancel-in-progress": True},
               "jobs": {"gate": {"runs-on": route, "timeout-minutes": 720}}}
        self.assertEqual(cr.check_workflow("firmware", "pr-gate.yml", doc), [])
        for value in (route.replace("'ghostnet-gate'", "'ghostnet-gateX'"),
                      route.replace("full_name ==", "full_name !="),
                      route.replace("github.event_name == 'pull_request' && ", "")):
            with self.subTest(route=value):
                self.assertNotEqual(cr.check_workflow("firmware", "pr-gate.yml",
                                                      {**doc, "jobs": {"gate": {"runs-on": value,
                                                                                "timeout-minutes": 720}}}), [])

    def test_unknown_or_modified_large_pool_routes_are_rejected(self):
        route = cr.arc_fork_fallback("ghostnet-linux-arm64-large")
        for value in ("ghostnet-linux-arm64-largeX", "ghostnet-linux-arm64-xl",
                      ["ghostnet-linux-arm64-large-spoof"],
                      route.replace("-large'", "-largeX'"),
                      route.replace("|| 'ubuntu-24.04'", "|| 'ghostnet-linux-arm64-large'"),
                      route.replace("full_name ==", "full_name !="),
                      route.replace("!= 'pull_request'", "== 'pull_request'"),
                      cr.arc_pr_only_fallback("ghostnet-linux-arm64-large").replace("event_name ==", "event_name !=")):
            with self.subTest(route=value):
                self.assertFalse(cr.is_self_hosted(value))
                self.assertFalse(cr.has_fork_guard(value))

    def test_large_pool_pr_only_route_still_checks_hosted_cron(self):
        doc = {"on": {"schedule": [{"cron": "*/15 * * * *"}]},
               "jobs": {"test": {"runs-on": cr.arc_pr_only_fallback("ghostnet-linux-arm64-large"),
                                 "timeout-minutes": 10}}}
        self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)), [("test", "hosted-cron")])

    def test_arc_cron_is_not_hosted_cron(self):
        doc = {"on": {"schedule": [{"cron": "*/15 * * * *"}]},
               "jobs": {"test": {"runs-on": "ghostnet-linux-arm64", "timeout-minutes": 10}}}
        self.assertEqual(cr.check_workflow("r", "w.yml", doc), [])

    def test_cancel_in_progress_expression_and_job_level(self):
        doc = wf("""
on: {pull_request: {}, push: {}}
concurrency:
  group: g
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
jobs:
  a: {runs-on: "${{ github.event.pull_request.head.repo.full_name == github.repository && 'self-hosted' || 'ubuntu-24.04' }}", timeout-minutes: 5, steps: []}
""")
        self.assertEqual(cr.check_workflow("r", "w.yml", doc), [])
        doc = wf("""
on: pull_request
concurrency: {group: g, cancel-in-progress: false}
jobs:
  a: {runs-on: "${{ github.event.pull_request.head.repo.full_name == github.repository && 'self-hosted' || 'ubuntu-24.04' }}", timeout-minutes: 5, concurrency: {group: j, cancel-in-progress: true}, steps: []}
  b: {runs-on: "${{ github.event.pull_request.head.repo.full_name == github.repository && 'self-hosted' || 'ubuntu-24.04' }}", timeout-minutes: 5, steps: []}
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
        hosted = wf(cron + "jobs: {a: {runs-on: ubuntu-24.04, timeout-minutes: 5, steps: []}}")
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


class LatestImageTest(unittest.TestCase):
    """2026-11-16: ubuntu-latest moved to 26.04 and openmanetd's Playwright job broke."""

    def job_rules(self, runs_on, on="push"):
        doc = {"on": on, "concurrency": {"group": "g", "cancel-in-progress": True},
               "jobs": {"j": {"runs-on": runs_on, "timeout-minutes": 5}}}
        return [r for _, r in rules(cr.check_workflow("r", "w.yml", doc))]

    def test_plain_latest_labels_are_flagged(self):
        for label in ("ubuntu-latest", "macos-latest", "windows-latest", ["ubuntu-latest"]):
            with self.subTest(label=label):
                self.assertIn("hosted-image-latest", self.job_rules(label))

    def test_latest_fork_fallback_is_flagged_but_route_still_recognized(self):
        for route in (cr.arc_fork_fallback("ghostnet-linux-arm64", "ubuntu-latest"),
                      cr.arc_pr_only_fallback("ghostnet-gate", "ubuntu-latest"),
                      "${{ github.event.pull_request.head.repo.full_name == github.repository && "
                      "fromJSON('[\"self-hosted\", \"macOS\", \"ARM64\"]') || 'ubuntu-latest' }}"):
            with self.subTest(route=route):
                self.assertTrue(cr.is_self_hosted(route))
                self.assertTrue(cr.has_fork_guard(route))
                self.assertEqual(self.job_rules(route, on="pull_request"), ["hosted-image-latest"])

    def test_pinned_images_pass(self):
        self.assertNotIn("hosted-image-latest", self.job_rules("ubuntu-24.04"))
        self.assertEqual(self.job_rules(cr.ARC_FORK_FALLBACK, on="pull_request"), [])
        self.assertIn(f"|| '{cr.HOSTED_IMAGE}' }}}}", cr.ARC_FORK_FALLBACK)

    def test_similar_names_are_not_latest(self):
        for label in ("ubuntu-latest-arm", "my-ubuntu-latest", "ghostnet-linux-arm64"):
            with self.subTest(label=label):
                self.assertNotIn("hosted-image-latest", self.job_rules(label))

    def test_finding_says_what_to_pin(self):
        doc = {"on": "push", "jobs": {"j": {"runs-on": "ubuntu-latest", "timeout-minutes": 5}}}
        detail = [f.detail for f in cr.check_workflow("r", "w.yml", doc) if f.rule == "hosted-image-latest"][0]
        self.assertIn("pin ubuntu-24.04", detail)


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
        (wfdir / "ci.yml").write_text("on: pull_request\njobs:\n  a: {runs-on: ubuntu-24.04, steps: []}\n")
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



SHA = "0123456789abcdef0123456789abcdef01234567"
STUDIO_JOB = f"""
  studio:
    name: Studio runners
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - uses: ghostnet-labs/docs/.github/actions/studio-runners@{SHA}
"""


class StudioFallbackTest(unittest.TestCase):
    """Routes that also go hosted while a Studio pool is offline (tools/studio-runners)."""

    def check(self, runs_on, on="pull_request", studio=STUDIO_JOB):
        doc = wf(f"""
on: {on}
concurrency: {{group: x, cancel-in-progress: true}}
jobs:{studio}
  t:
    needs: studio
    runs-on: {runs_on}
    timeout-minutes: 10
    steps: []
""")
        return rules(cr.check_workflow("r", "w.yml", doc))

    def test_mac_plain_form(self):
        ro = ("${{ github.event.pull_request.head.repo.full_name == github.repository && "
              "needs.studio.outputs.mac != 'false' && fromJSON('[\"self-hosted\", \"macOS\", \"ARM64\"]') "
              "|| 'ubuntu-24.04' }}")
        self.assertEqual(self.check(ro), [])

    def test_arc_event_form(self):
        ro = ("${{ (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == "
              "github.repository) && needs.studio.outputs.arc != 'false' && 'ghostnet-linux-arm64' || 'ubuntu-24.04' }}")
        self.assertEqual(self.check(ro, on="[pull_request, push]"), [])

    def test_arc_pr_only_form(self):
        ro = ("${{ github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == "
              "github.repository && needs.studio.outputs.arc != 'false' && 'ghostnet-gate' || 'ubuntu-24.04' }}")
        self.assertEqual(self.check(ro), [])

    def test_build_form(self):
        ro = ("${{ github.event.pull_request.head.repo.full_name == github.repository && "
              "needs.studio.outputs.build != 'false' && fromJSON('[\"self-hosted\", \"openwrt-build\"]') "
              "|| 'ubuntu-24.04' }}")
        self.assertEqual(self.check(ro), [])

    def test_pool_must_match_labels(self):
        ro = ("${{ github.event.pull_request.head.repo.full_name == github.repository && "
              "needs.studio.outputs.arc != 'false' && fromJSON('[\"self-hosted\", \"macOS\", \"ARM64\"]') "
              "|| 'ubuntu-24.04' }}")
        self.assertEqual(self.check(ro), [("t", "fork-pr-self-hosted")])

    def test_term_cannot_replace_the_fork_guard(self):
        ro = ("${{ needs.studio.outputs.mac != 'false' && fromJSON('[\"self-hosted\", \"macOS\", \"ARM64\"]') "
              "|| 'ubuntu-24.04' }}")
        self.assertEqual(self.check(ro), [("t", "fork-pr-self-hosted")])

    def test_inverted_term_rejected(self):
        ro = ("${{ github.event.pull_request.head.repo.full_name == github.repository && "
              "needs.studio.outputs.mac == 'false' && fromJSON('[\"self-hosted\", \"macOS\", \"ARM64\"]') "
              "|| 'ubuntu-24.04' }}")
        self.assertEqual(self.check(ro), [("t", "fork-pr-self-hosted")])

    def test_reusable_input_form(self):
        doc = wf("""
on: {workflow_call: {inputs: {studio_mac: {type: string, default: 'true'}}}}
jobs:
  t:
    runs-on: ${{ github.event.pull_request.head.repo.full_name == github.repository && inputs.studio_mac != 'false' && fromJSON('["self-hosted", "macOS", "ARM64"]') || 'ubuntu-24.04' }}
    timeout-minutes: 10
    steps: []
""")
        self.assertEqual(rules(cr.check_workflow("r", "w.yml", doc)), [])

    def test_selector_needs_pinned_action(self):
        unpinned = STUDIO_JOB.replace(f"@{SHA}", "@main")
        self.assertEqual(self.check("ubuntu-24.04", studio=unpinned),
                         [("studio", "hosted-runner"), ("t", "hosted-runner")])

    def test_selector_must_be_only_that_step(self):
        extra = STUDIO_JOB + "      - run: echo hi\n"
        self.assertIn(("studio", "hosted-runner"), self.check("ubuntu-24.04", studio=extra))

    def test_selector_on_latest_image_is_a_finding(self):
        latest = STUDIO_JOB.replace("runs-on: ubuntu-24.04", "runs-on: ubuntu-latest")
        self.assertIn(("studio", "hosted-runner"), self.check("ubuntu-24.04", studio=latest))


sys.path.insert(0, str(ROOT / "project" / "scripts"))
import add_studio_fallback as asf  # noqa: E402

GATE = """name: Manet merge gate
on:
  pull_request:
    types: [opened, synchronize, closed]
permissions:
  contents: read
concurrency:
  group: manet-gate-${{ github.event.pull_request.number }}
  cancel-in-progress: true
jobs:
  gate:
    name: Manet merge gate
    if: github.event.action != 'closed'
    runs-on: ${{ github.event.pull_request.head.repo.full_name == github.repository && fromJSON('["self-hosted", "macOS", "ARM64"]') || 'ubuntu-24.04' }}
    timeout-minutes: 350
    steps:
      - run: echo gate
"""

TESTS = """name: Go tests
on: [pull_request, workflow_dispatch]
concurrency: {group: x, cancel-in-progress: true}
jobs:
  lint:
    runs-on: ${{ (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) && 'ghostnet-linux-arm64' || 'ubuntu-24.04' }}
    timeout-minutes: 10
    steps: []
  test:
    needs: lint
    runs-on: ${{ (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) && 'ghostnet-linux-arm64' || 'ubuntu-24.04' }}
    timeout-minutes: 10
    steps: []
"""


class AddStudioFallbackTest(unittest.TestCase):
    def test_gate_passes_policy(self):
        out = asf.apply(GATE, SHA, {"gate": "mac"}, "github.event.action != 'closed'")
        doc = yaml.safe_load(out)
        self.assertEqual(cr.check_workflow("r", "w.yml", doc), [])
        gate = doc["jobs"]["gate"]
        self.assertEqual(gate["needs"], "studio")
        self.assertEqual(gate["if"], "${{ !cancelled() && github.event.action != 'closed' }}")
        self.assertIn("needs.studio.outputs.mac != 'false' && fromJSON", gate["runs-on"])
        self.assertEqual(doc["jobs"]["studio"]["if"], "github.event.action != 'closed'")

    def test_chained_jobs_keep_their_needs(self):
        out = asf.apply(TESTS, SHA, {"lint": "arc", "test": "arc"})
        doc = yaml.safe_load(out)
        self.assertEqual(cr.check_workflow("r", "w.yml", doc), [])
        test = doc["jobs"]["test"]
        self.assertEqual(test["needs"], ["lint", "studio"])
        self.assertEqual(test["if"], "${{ !cancelled() && needs.lint.result == 'success' }}")

    def test_rerun_moves_only_the_pin(self):
        once = asf.apply(GATE, SHA, {"gate": "mac"})
        other = "f" * 40
        twice = asf.apply(once, other, {"gate": "mac"})
        self.assertEqual(twice, once.replace(SHA, other))
