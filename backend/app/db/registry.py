"""Import every model module so the metadata objects are complete (Alembic autogenerate, tests)."""

from __future__ import annotations

import app.master.models
import app.modules.core.models
import app.modules.identity.models
import app.modules.rbac.models
import app.modules.rbac.service  # noqa: F401  (registers seeders)
from app.db.base import MasterBase, TenantBase

master_metadata = MasterBase.metadata
tenant_metadata = TenantBase.metadata
