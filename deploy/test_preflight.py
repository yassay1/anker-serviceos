"""Offline checks: no database, cloud, Docker daemon or model calls."""

import copy
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from preflight import CA_PATH, main, validate


class ProductionPreflightTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "SERVICEOS_ENV": "production",
            "SERVICEOS_AUTH_MODE": "disabled",
            "SERVICEOS_DATABASE_URL": (
                "postgresql+psycopg://serviceos:secret-sentinel@db.example.invalid:5432/serviceos"
                f"?sslmode=verify-full&sslrootcert={CA_PATH}"
            ),
            "SERVICEOS_PUBLIC_HOSTNAME": "service.example.invalid",
            "SERVICEOS_ALLOWED_ORIGINS": "https://service.example.invalid",
            "SERVICEOS_EVIDENCE_STORAGE_BACKEND": "s3",
            "SERVICEOS_S3_BUCKET": "private-evidence-example",
            "SERVICEOS_S3_REGION": "us-east-1",
            "SERVICEOS_S3_PREFIX": "production/evidence",
        }
        # CA parsing only is replaced. URL and isolation rules run unmodified.
        self.ca_parser = patch("preflight.ssl.create_default_context")
        self.ca_parser.start()
        self.addCleanup(self.ca_parser.stop)

    def rejected(self, key, value, code):
        environment = copy.deepcopy(self.environment)
        environment[key] = value
        with self.assertRaisesRegex(ValueError, f"^{code}$"):
            validate(environment)

    def test_valid_transport_does_not_claim_production_readiness(self):
        with patch.dict("os.environ", self.environment, clear=True):
            output = io.StringIO()
            with redirect_stdout(output):
                main()
        self.assertIn("identity is DISABLED", output.getvalue())
        self.assertNotIn("secret-sentinel", output.getvalue())

    def test_local_auth_and_environment_are_rejected(self):
        self.rejected("SERVICEOS_ENV", "development", "production_environment_required")
        self.rejected("SERVICEOS_AUTH_MODE", "local", "production_identity_integration_not_implemented")

    def test_tls_downgrade_and_duplicate_tls_options_are_rejected(self):
        url = self.environment["SERVICEOS_DATABASE_URL"]
        for unsafe in (url.replace("verify-full", "require"), url.replace("verify-full", "disable"),
                       url + "&sslmode=disable", url.split("?")[0]):
            self.rejected("SERVICEOS_DATABASE_URL", unsafe, "database_verify_full_and_mounted_ca_required")

    def test_connection_destination_override_is_rejected(self):
        self.rejected("SERVICEOS_DATABASE_URL", self.environment["SERVICEOS_DATABASE_URL"] + "&host=localhost",
                      "database_query_option_not_allowed")

    def test_local_database_is_rejected(self):
        self.rejected("SERVICEOS_DATABASE_URL", self.environment["SERVICEOS_DATABASE_URL"].replace(
            "db.example.invalid", "127.0.0.1"), "external_postgresql_url_required")

    def test_invalid_url_is_safely_reported(self):
        self.rejected("SERVICEOS_DATABASE_URL", "postgresql+psycopg://[bad-secret-sentinel", "database_url_invalid")

    def test_ca_failure_is_safely_reported(self):
        with patch("preflight.ssl.create_default_context", side_effect=OSError("secret-sentinel")):
            with self.assertRaisesRegex(ValueError, "^database_ca_unreadable_or_invalid$"):
                validate(self.environment)

    def test_nginx_hostname_injection_and_wildcard_origin_are_rejected(self):
        self.rejected("SERVICEOS_PUBLIC_HOSTNAME", "example.invalid; return 200;", "public_dns_hostname_required")
        self.rejected("SERVICEOS_ALLOWED_ORIGINS", "*", "same_origin_https_required")

    def test_local_storage_and_unsafe_prefix_are_rejected(self):
        self.rejected("SERVICEOS_EVIDENCE_STORAGE_BACKEND", "local", "private_s3_required")
        for prefix in ("", "/root", "production/../other"):
            self.rejected("SERVICEOS_S3_PREFIX", prefix, "dedicated_s3_prefix_required")

    def test_cli_failure_does_not_leak_credentials(self):
        self.environment["SERVICEOS_DATABASE_URL"] += "&password=secret-sentinel"
        with patch.dict("os.environ", self.environment, clear=True):
            with self.assertRaises(SystemExit) as failure:
                main()
        self.assertEqual(str(failure.exception), "Production preflight failed: database_query_option_not_allowed")


if __name__ == "__main__":
    unittest.main()
