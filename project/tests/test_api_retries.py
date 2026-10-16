"""Transient GitHub API errors are retried for reads and never for writes."""
import http.client
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import merge_policy
from merge_policy import API


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def ok(payload):
    return FakeResponse(json.dumps(payload).encode())


def http_error(code):
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", {}, io.BytesIO(b"{}"))


class APIRetryTests(unittest.TestCase):
    def call(self, outcomes, **kwargs):
        sleeps = []
        with mock.patch.object(merge_policy.urllib.request, "urlopen", side_effect=outcomes) as urlopen, \
                mock.patch.object(merge_policy.time, "sleep", sleeps.append):
            try:
                result = API("t").call("repos/o/r/pulls/1", **kwargs)
            except Exception as error:  # noqa: BLE001 - tests assert on the raised type
                result = error
        return result, urlopen.call_count, sleeps

    def test_read_retries_transient_errors_then_succeeds(self):
        for error in (http.client.IncompleteRead(b"x", 5), http.client.RemoteDisconnected("closed"),
                      urllib.error.URLError("reset"), TimeoutError(), ConnectionResetError(), http_error(502),
                      http_error(429)):
            with self.subTest(error=type(error).__name__):
                result, calls, sleeps = self.call([error, ok({"n": 1})])
                self.assertEqual(result, {"n": 1})
                self.assertEqual(calls, 2)
                self.assertEqual(sleeps, [merge_policy.RETRY_BASE_DELAY])

    def test_backoff_doubles_and_gives_up_after_the_last_attempt(self):
        errors = [http.client.RemoteDisconnected("closed")] * merge_policy.READ_ATTEMPTS
        result, calls, sleeps = self.call(errors)
        self.assertIsInstance(result, http.client.RemoteDisconnected)
        self.assertEqual(calls, merge_policy.READ_ATTEMPTS)
        self.assertEqual(sleeps, [merge_policy.RETRY_BASE_DELAY * 2 ** i
                                  for i in range(merge_policy.READ_ATTEMPTS - 1)])

    def test_client_errors_are_not_retried(self):
        for code in (401, 403, 404, 422):
            with self.subTest(code=code):
                result, calls, sleeps = self.call([http_error(code), ok({})])
                self.assertIsInstance(result, urllib.error.HTTPError)
                self.assertEqual((calls, sleeps), (1, []))

    def test_writes_are_never_retried(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                result, calls, sleeps = self.call([http.client.RemoteDisconnected("closed"), ok({})],
                                                  data={"a": 1}, method=method)
                self.assertIsInstance(result, http.client.RemoteDisconnected)
                self.assertEqual((calls, sleeps), (1, []))


if __name__ == "__main__":
    unittest.main()
