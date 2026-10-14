"""Offline production transport checks; success is NOT identity readiness."""

import os
from pathlib import Path
import re
import ssl
from urllib.parse import parse_qs, urlsplit


CA_PATH = "/etc/serviceos/rds/global-bundle.pem"


def validate(environment, ca_path=CA_PATH):
    if environment.get("SERVICEOS_ENV") != "production":
        raise ValueError("production_environment_required")
    if environment.get("SERVICEOS_AUTH_MODE") != "disabled":
        raise ValueError("production_identity_integration_not_implemented")
    try:
        url = urlsplit(environment.get("SERVICEOS_DATABASE_URL", ""))
        query = parse_qs(url.query, keep_blank_values=True)
        port = url.port
        host = url.hostname
    except ValueError:
        raise ValueError("database_url_invalid") from None
    if (url.scheme != "postgresql+psycopg" or not host or host in ("localhost", "127.0.0.1", "::1")
            or not url.username or not url.password or url.path in ("", "/") or url.fragment
            or port not in (None, 5432)):
        raise ValueError("external_postgresql_url_required")
    # A query-level host/service override could silently change the TLS target.
    if set(query) - {"sslmode", "sslrootcert", "connect_timeout", "application_name"}:
        raise ValueError("database_query_option_not_allowed")
    if query.get("sslmode") != ["verify-full"] or query.get("sslrootcert") != [CA_PATH]:
        raise ValueError("database_verify_full_and_mounted_ca_required")
    try:
        ssl.create_default_context(cafile=str(Path(ca_path)))
    except (OSError, ssl.SSLError):
        raise ValueError("database_ca_unreadable_or_invalid") from None
    hostname = environment.get("SERVICEOS_PUBLIC_HOSTNAME", "")
    if (len(hostname) > 253 or not re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", hostname)):
        raise ValueError("public_dns_hostname_required")
    if environment.get("SERVICEOS_ALLOWED_ORIGINS") != f"https://{hostname}":
        raise ValueError("same_origin_https_required")
    if environment.get("SERVICEOS_EVIDENCE_STORAGE_BACKEND") != "s3":
        raise ValueError("private_s3_required")
    if not environment.get("SERVICEOS_S3_BUCKET") or not environment.get("SERVICEOS_S3_REGION"):
        raise ValueError("s3_bucket_and_region_required")
    prefix = environment.get("SERVICEOS_S3_PREFIX", "")
    if not prefix or prefix.startswith("/") or ".." in prefix.split("/"):
        raise ValueError("dedicated_s3_prefix_required")


def main():
    try:
        validate(os.environ)
    except ValueError as error:
        # Only our fixed codes; never interpolate URLs, credentials or exceptions.
        raise SystemExit(f"Production preflight failed: {error}") from None
    print("Transport configuration validated offline; production identity is DISABLED. Not approved for traffic.")


if __name__ == "__main__":
    main()
