import contextlib
import io
import unittest
from unittest.mock import Mock, patch

from traversal import __main__ as cli


class BootstrapRoleTests(unittest.TestCase):
    def bootstrap(self, existing):
        with (
            patch.object(cli.sys, "argv", ["traversal", "bootstrap"]),
            patch.dict(cli.os.environ, {
                "DATABASE_URL": "postgresql://bootstrap-test",
                "APP_DATABASE_URL": "postgresql://runtime-test",
                "APP_DATABASE_PASSWORD": "unit-test-password",
            }),
            patch.object(cli, "load_graph", return_value="test_graph"),
            patch.object(cli, "AgeGraph"),
            patch("traversal.server.initialize_app_store"),
            patch.object(cli.psycopg, "connect") as connect,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            connection = connect.return_value.__enter__.return_value
            connection.execute.side_effect = [
                Mock(fetchone=Mock(return_value=existing)),
                Mock(),
                Mock(fetchone=Mock(return_value=(False, False, False))),
                Mock(fetchone=Mock(return_value=(False,))),
            ]
            cli.main()
            return connection.execute.call_args_list[1].args[0].as_string()

    def test_creation_explicitly_disables_administrative_attributes(self):
        statement = self.bootstrap(None)
        self.assertTrue(statement.startswith('CREATE ROLE "traversal_app"'))
        self.assertIn("NOSUPERUSER NOCREATEDB NOCREATEROLE", statement)

    def test_repeat_bootstrap_does_not_require_superuser_attribute_access(self):
        statement = self.bootstrap((False,))
        self.assertTrue(statement.startswith('ALTER ROLE "traversal_app"'))
        self.assertNotIn("SUPERUSER", statement)
        self.assertIn("NOCREATEDB NOCREATEROLE", statement)

    def test_existing_superuser_role_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "existing superuser"):
            self.bootstrap((True,))


if __name__ == "__main__":
    unittest.main()
