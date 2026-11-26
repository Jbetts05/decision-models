import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compliance import foundry  # noqa: E402

CONFIG = {"endpoint": "https://example.cognitiveservices.azure.com", "decision_deployment": "d",
          "auth_mode": "azure_cli", "timeout_seconds": 5, "daily_max_calls": 10}


class FoundryTests(unittest.TestCase):
    def test_rate_limits_are_retried_then_reported(self):
        client = foundry.Foundry(CONFIG)
        with mock.patch.object(client, "_post_once", side_effect=foundry._RateLimited(0)) as call, \
                mock.patch.object(foundry.time, "sleep"):
            with self.assertRaisesRegex(foundry.FoundryError, "429"):
                client.post("/x", {})
        self.assertEqual(call.call_count, 3)

    def test_rate_limit_then_success(self):
        client = foundry.Foundry(CONFIG)
        outcomes = [foundry._RateLimited(0), ({"ok": True}, 1.0)]

        def step(*args):
            item = outcomes.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        with mock.patch.object(client, "_post_once", side_effect=step), mock.patch.object(foundry.time, "sleep"):
            self.assertEqual(client.post("/x", {})[0], {"ok": True})

    def test_long_retry_after_is_not_cut_short(self):
        client = foundry.Foundry(CONFIG)
        with mock.patch.object(client, "_post_once", side_effect=foundry._RateLimited(60)) as call, \
                mock.patch.object(foundry.time, "sleep") as sleep:
            with self.assertRaisesRegex(foundry.FoundryError, "429"):
                client.post("/x", {})
        self.assertEqual(call.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(foundry.retry_after_seconds("7"), 7.0)
        self.assertEqual(foundry.retry_after_seconds("not a date"), 0.0)

    def test_endpoint_validation(self):
        for bad in ("http://example.cognitiveservices.azure.com", "https://evil.example.com",
                    "https://example.cognitiveservices.azure.com/path", "https://user@example.cognitiveservices.azure.com"):
            with self.assertRaises(ValueError):
                foundry.validate_endpoint(bad)
        self.assertEqual(foundry.validate_endpoint("https://a.services.ai.azure.com/"), "https://a.services.ai.azure.com")


if __name__ == "__main__":
    unittest.main()
