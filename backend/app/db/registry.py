"""Import every model module so the metadata objects are complete (Alembic autogenerate, tests)."""

from __future__ import annotations

import app.master.models
import app.modules.core.models
import app.modules.identity.models  # noqa: F401
from app.db.base import MasterBase, TenantBase

master_metadata = MasterBase.metadata
tenant_metadata = TenantBase.metadata
