import base64
import io
import json
import os
import sys
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_sync as ps

WF = ".github/workflows/"
PR = "on:\n  pull_request:\n    paths:\n      - a/**\n"
OLD, NEW = "a" * 40, "b" * 40
PIN_YML = ("steps:\n  - uses: actions/checkout@v4\n    with:\n      repository: ghostnet-labs/docs\n"
           "      ref: {sha}\n      persist-credentials: false\n  - uses: actions/checkout@v4\n    with:\n"
           "      repository: ghostnet-labs/docs\n      ref: {tool}\n      path: tool\n      persist-credentials: false\n")
TOOL = "c" * 40


def b64(text):
    return {"content": base64.b64encode(text.encode()).decode(), "sha": "blob"}


class FakeAPI:
    """Just enough of GitHub for profile_sync: one repo r with one workflow."""

    def __init__(self, profile_entries, workflows, pin=OLD, pinned_profile=None, policy_at_pin="p1"):
        self.docs_profile = {"r": {"branch": "main", "workflows": profile_entries}}
        self.workflows = workflows
        self.pin = pin
        self.pinned_profile = self.docs_profile if pinned_profile is None else pinned_profile
        self.policy_at_pin = policy_at_pin
        self.writes = []
        self.open_prs = {}

    def call(self, path, data=None, method=None):
        if method in ("PUT", "PATCH", "POST"):
            self.writes.append((method, path, data))
            if path.endswith("/pulls") and method == "POST":
                return {"html_url": "https://github.com/" + path.split("repos/")[1].split("/pulls")[0] + "/pull/1"}
            return {}
        if "/contents/.github/workflows?" in path:
            return [{"type": "file", "name": n.split("/")[-1], "path": n} for n in self.workflows]
        if "/contents/" in path:
            repo, rest = path.split("repos/")[1].split("/contents/")
            name, ref = rest.split("?ref=")
            if repo.endswith("/docs"):
                if name == ps.PROFILE_PATH:
                    return b64(json.dumps(self.docs_profile if ref == "main" else self.pinned_profile))
                return b64("p2" if ref in ("main", NEW) else self.policy_at_pin)
            if name in self.workflows:
                return b64(self.workflows[name])
            if name in ps.PIN_FILES:
                return b64(PIN_YML.format(sha=self.pin, tool=TOOL))
            raise urllib.error.HTTPError(path, 404, "nf", {}, None)
        if "/commits?" in path:
            return [{"sha": NEW}]
        if "/git/ref/" in path:
            return {"object": {"sha": "base"}}
        if "/pulls?state=open" in path:
            return self.open_prs.get(path, [])
        raise AssertionError(path)


class ProfileSyncTests(unittest.TestCase):
    def run_sync(self, api):
        out = io.StringIO()
        with redirect_stdout(out):
            ps.run(api)
        return out.getvalue()

    def test_skips_without_token(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"MANET_UPDATE_TOKEN": ""}), redirect_stdout(out):
            self.assertEqual(ps.main(), 0)
        self.assertIn("skip", out.getvalue())

    def test_workflow_missing_from_profile_opens_one_docs_pr_with_new_profile(self):
        api = FakeAPI([], {WF + "new.yml": PR})
        out = self.run_sync(api)
        self.assertIn("profile PR: https://github.com/ghostnet-labs/docs/pull/1", out)
        put = [w for w in api.writes if w[0] == "PUT"][0]
        written = json.loads(base64.b64decode(put[2]["content"]))
        self.assertEqual(written["r"]["workflows"], [{"path": WF + "new.yml", "paths": ["a/**"]}])
        self.assertEqual(put[2]["branch"], ps.PROFILE_BRANCH)
        self.assertFalse([w for w in api.writes if "/ghostnet-labs/r/" in w[1]])  # no pin PR until profile lands

    def test_existing_pr_is_updated_not_duplicated(self):
        api = FakeAPI([], {WF + "new.yml": PR})
        api.open_prs["repos/ghostnet-labs/docs/pulls?state=open&head=ghostnet-labs:" + ps.PROFILE_BRANCH] = [
            {"number": 9, "html_url": "https://github.com/ghostnet-labs/docs/pull/9"}]
        self.assertIn("pull/9", self.run_sync(api))
        self.assertFalse([w for w in api.writes if w[0] == "POST" and w[1].endswith("/pulls")])

    def test_stale_pin_opens_pin_pr_moving_only_the_policy_checkout(self):
        entries = [{"path": WF + "new.yml", "paths": ["a/**"]}]
        api = FakeAPI(entries, {WF + "new.yml": PR}, pinned_profile={"r": {"branch": "main", "workflows": []}})
        out = self.run_sync(api)
        self.assertIn("pin PR: https://github.com/ghostnet-labs/r/pull/1", out)
        puts = [w for w in api.writes if w[0] == "PUT"]
        self.assertEqual(len(puts), 2)
        text = base64.b64decode(puts[0][2]["content"]).decode()
        self.assertIn("ref: " + NEW, text)
        self.assertIn("ref: " + TOOL, text)
        self.assertEqual(text.count(OLD), 0)

    def test_policy_change_alone_makes_pin_stale(self):
        entries = [{"path": WF + "new.yml", "paths": ["a/**"]}]
        api = FakeAPI(entries, {WF + "new.yml": PR}, policy_at_pin="old policy")
        self.assertIn("pin PR", self.run_sync(api))

    def test_up_to_date_pin_and_profile_do_nothing(self):
        entries = [{"path": WF + "new.yml", "paths": ["a/**"]}]
        api = FakeAPI(entries, {WF + "new.yml": PR}, policy_at_pin="p2")
        self.assertIn("profiles match", self.run_sync(api))
        self.assertEqual(api.writes, [])

    def test_pin_already_on_docs_main_is_left_alone(self):
        entries = [{"path": WF + "new.yml", "paths": ["a/**"]}]
        api = FakeAPI(entries, {WF + "new.yml": PR}, pin=NEW, policy_at_pin="old policy")
        self.run_sync(api)
        self.assertEqual(api.writes, [])


if __name__ == "__main__":
    unittest.main()
