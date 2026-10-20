import contextlib
import io
import subprocess
import unittest
from unittest.mock import call, patch

from traversal import __main__ as cli


class StartTests(unittest.TestCase):
    @contextlib.contextmanager
    def start_context(self, config, error=None):
        with (
            patch.object(cli.sys, "argv", ["traversal", "start", "--port", "8876"]),
            patch.object(cli, "load_config", return_value=config),
            patch.object(cli, "database_url", return_value="postgresql://local-test"),
            patch.object(cli.subprocess, "run", side_effect=error) as run,
            patch("traversal.server.serve") as serve,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            yield run, serve

    def configuration(self):
        return {
            "endpoint": "https://example.cognitiveservices.azure.com",
            "decision_deployment": "Decision-1",
            "baseline_deployment": "Sol",
        }

    def test_start_reuses_current_python_and_frozen_data_without_inference(self):
        config = self.configuration()
        with self.start_context(config) as (run, serve), patch.object(cli.Foundry, "post") as inference:
            cli.main()
            self.assertEqual(run.call_args_list, [
                call([cli.sys.executable, "-m", "traversal", command], check=True)
                for command in ("validate", "db-up", "load")
            ])
            serve.assert_called_once_with("postgresql://local-test", config, cli.DATA, 8876)
            inference.assert_not_called()

    def test_placeholders_fail_before_database_start(self):
        for key in ("endpoint", "decision_deployment", "baseline_deployment"):
            config = self.configuration()
            config[key] = "https://YOUR-RESOURCE.cognitiveservices.azure.com" if key == "endpoint" else "YOUR-DEPLOYMENT"
            with self.subTest(key=key), self.start_context(config) as (run, serve):
                with self.assertRaisesRegex(ValueError, f"Replace the {key} placeholder"):
                    cli.main()
                run.assert_not_called()
                serve.assert_not_called()

    def test_invalid_endpoint_fails_before_database_start(self):
        config = self.configuration()
        config["endpoint"] = "https://example.org"
        with self.start_context(config) as (run, serve):
            with self.assertRaisesRegex(ValueError, "Foundry HTTPS resource endpoint"):
                cli.main()
            run.assert_not_called()
            serve.assert_not_called()

    def test_child_failure_is_not_hidden_or_followed_by_serve(self):
        error = subprocess.CalledProcessError(1, "validate")
        with self.start_context(self.configuration(), error) as (run, serve):
            with self.assertRaises(subprocess.CalledProcessError):
                cli.main()
            self.assertEqual(run.call_count, 1)
            serve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
