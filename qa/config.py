"""Where the gate connects and which schemas it reads / writes.

Everything comes from environment variables, so no credential ever lives in the repository:

    QA_BACKEND          databricks (default) | spark (local test harness)
    QA_CATALOG          Unity Catalog name on Databricks (default: workspace)
    QA_SCHEMA_PREFIX    dbt development schema, e.g. dbt_rwang -> dbt_rwang_marts, dbt_rwang_ops ...
                        Set it to an empty string for production (bare schema names: marts, ops ...)
    QA_RUN_BY           who is running the gate (default: the OS user)

    DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN   (Databricks backend only)
"""

from __future__ import annotations

import getpass
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    backend: str
    catalog: str | None
    schema_prefix: str
    run_by: str

    @classmethod
    def from_env(cls) -> "Settings":
        backend = os.environ.get("QA_BACKEND", "databricks").strip().lower()
        if backend not in {"databricks", "spark"}:
            raise ValueError(f"QA_BACKEND must be 'databricks' or 'spark', got {backend!r}")
        catalog = os.environ.get("QA_CATALOG", "workspace").strip() if backend == "databricks" else None
        return cls(
            backend=backend,
            catalog=catalog or None,
            schema_prefix=os.environ.get("QA_SCHEMA_PREFIX", "dbt_rwang").strip(),
            run_by=os.environ.get("QA_RUN_BY") or getpass.getuser(),
        )

    def schema(self, layer: str) -> str:
        """Fully qualified schema of a dbt layer, mirroring dbt's generate_schema_name macro."""
        name = f"{self.schema_prefix}_{layer}" if self.schema_prefix else layer
        return f"{self.catalog}.{name}" if self.catalog else name

    def placeholders(self) -> dict[str, str]:
        return {
            "marts": self.schema("marts"),
            "intermediate": self.schema("intermediate"),
            "ops": self.schema("ops"),
        }
