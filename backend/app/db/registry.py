"""Import every model module so the metadata objects are complete (Alembic autogenerate, tests),
and every module that registers seeders or session hooks."""

from __future__ import annotations

import app.master.models
import app.modules.activities.models
import app.modules.activities.service  # workflow handlers
import app.modules.attachments.models
import app.modules.core.models
import app.modules.identity.models
import app.modules.notifications.models
import app.modules.notifications.service  # after_commit delivery hooks
import app.modules.org_units.models
import app.modules.org_units.service  # seeder + RBAC org-unit resolver
import app.modules.parish.models
import app.modules.parish.service  # profile seeder
import app.modules.people.models
import app.modules.rbac.models
import app.modules.rbac.service  # RBAC seeder
import app.modules.workflow.models
import app.modules.workflow.seeds  # default workflows
from app.db.base import MasterBase, TenantBase

LOADED_MODULES = (
    app.master.models,
    app.modules.activities.models,
    app.modules.activities.service,
    app.modules.attachments.models,
    app.modules.core.models,
    app.modules.identity.models,
    app.modules.notifications.models,
    app.modules.notifications.service,
    app.modules.org_units.models,
    app.modules.org_units.service,
    app.modules.parish.models,
    app.modules.parish.service,
    app.modules.people.models,
    app.modules.rbac.models,
    app.modules.rbac.service,
    app.modules.workflow.models,
    app.modules.workflow.seeds,
)

master_metadata = MasterBase.metadata
tenant_metadata = TenantBase.metadata
