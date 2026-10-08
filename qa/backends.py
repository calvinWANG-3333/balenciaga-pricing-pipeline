"""Two ways to reach the warehouse, one interface: query(sql) -> list of dicts, execute(sql).

DatabricksBackend  the real thing: the Databricks SQL warehouse, over the official SQL connector.
SparkBackend       a local Spark session with the dbt project built into its metastore - the test
                   harness used to develop this project without spending warehouse credits.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from .config import Settings


class Backend(Protocol):
    def query(self, sql: str) -> list[dict[str, Any]]: ...
    def execute(self, sql: str) -> None: ...
    def close(self) -> None: ...


def _use_system_trust_store() -> bool:
    """Make Python trust the same certificates as the operating system (and the browser).

    Python ships its own list of trusted certificate authorities and ignores the macOS Keychain. On a
    network that re-signs HTTPS traffic (company or school network, VPN, antivirus), the browser works
    - its Keychain trusts the re-signing authority - but Python fails with CERTIFICATE_VERIFY_FAILED.
    `truststore` (from the pip maintainers) points Python at the system store. Verification stays ON.
    """
    try:
        import truststore
    except ImportError:
        return False
    truststore.inject_into_ssl()
    return True


def _preflight(host: str) -> None:
    """Fail in seconds with a readable message, instead of after 15 minutes of connector retries."""
    import socket
    import ssl

    try:
        socket.getaddrinfo(host, 443)
    except socket.gaierror as exc:
        raise SystemExit(
            f"Cannot resolve {host!r}: the computer cannot find this address.\n"
            "  - check DATABRICKS_SERVER_HOSTNAME (just the host: no https://, no trailing /)\n"
            "  - check your internet connection / VPN, then retry") from exc
    try:
        with socket.create_connection((host, 443), timeout=15) as sock:
            with ssl.create_default_context().wrap_socket(sock, server_hostname=host):
                pass
    except ssl.SSLCertVerificationError as exc:
        raise SystemExit(
            f"TLS check failed for {host}: {exc.verify_message}.\n"
            "Something between this computer and Databricks re-signs HTTPS traffic (school / company\n"
            "network, VPN or proxy app, antivirus web shield). See docs/07_delivery_gate.md, section 4,\n"
            "'CERTIFICATE_VERIFY_FAILED'. Never switch certificate verification off.") from exc
    except OSError as exc:
        raise SystemExit(f"Cannot open a connection to {host}:443 ({exc}). Check your network / VPN.") from exc


class DatabricksBackend:
    def __init__(self) -> None:
        try:
            from databricks import sql as dbsql
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise SystemExit("pip install -r qa/requirements.txt  (databricks-sql-connector is missing)") from exc

        missing = [v for v in ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")
                   if not os.environ.get(v)]
        if missing:
            raise SystemExit(f"Missing environment variable(s): {', '.join(missing)} (see docs/07_delivery_gate.md)")

        # tolerate a pasted URL: keep only the host name
        host = os.environ["DATABRICKS_SERVER_HOSTNAME"].strip().removeprefix("https://").rstrip("/")
        _use_system_trust_store()
        _preflight(host)

        extra = {}
        if os.environ.get("DATABRICKS_CA_BUNDLE"):          # last resort: an exported root certificate (PEM)
            extra["_tls_trusted_ca_file"] = os.environ["DATABRICKS_CA_BUNDLE"]

        self._conn = dbsql.connect(
            server_hostname=host,
            http_path=os.environ["DATABRICKS_HTTP_PATH"].strip(),
            access_token=os.environ["DATABRICKS_TOKEN"].strip(),
            # give up after 5 minutes instead of the default 15 (a sleeping warehouse wakes in < 2)
            _retry_stop_after_attempts_duration=300,
            # no usage telemetry to Databricks from this tool
            enable_telemetry=False,
            **extra,
        )

    def query(self, sql: str) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(sql)
            columns = [c[0] for c in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def execute(self, sql: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(sql)

    def close(self) -> None:
        self._conn.close()


class SparkBackend:
    def __init__(self) -> None:
        from pyspark.sql import SparkSession

        self._spark = SparkSession.builder.enableHiveSupport().getOrCreate()
        self._spark.sparkContext.setLogLevel("ERROR")

    def query(self, sql: str) -> list[dict[str, Any]]:
        return [row.asDict() for row in self._spark.sql(sql).collect()]

    def execute(self, sql: str) -> None:
        self._spark.sql(sql)

    def close(self) -> None:
        pass


def connect(settings: Settings) -> Backend:
    return DatabricksBackend() if settings.backend == "databricks" else SparkBackend()
