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

        self._conn = dbsql.connect(
            server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
            http_path=os.environ["DATABRICKS_HTTP_PATH"],
            access_token=os.environ["DATABRICKS_TOKEN"],
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
