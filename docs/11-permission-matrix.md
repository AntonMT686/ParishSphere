# 11 — Role & Permission Matrix

_Generated from `backend/app/modules/rbac/catalog.py` by `backend/scripts/gen_permission_matrix.py`._
These are the **default** grants seeded into every new parish; parish administrators can edit them.

## Roles

| Abbr | Code | Name | Scope | Description |
|---|---|---|---|---|
| Adm | `PARISH_ADMIN` | Parish Administrator | PARISH | Configures users, roles, workflows, organisations and settings. |
| Pri | `PARISH_PRIEST` | Parish Priest | PARISH | Final authority: full visibility and final approval on every workflow. |
| Pre | `PARISH_PRESIDENT` | Parish President | PARISH | Leads the parish council; reviews committee work. |
| Sec | `PARISH_SECRETARY` | Parish Secretary | PARISH | Maintains parish registers, meetings and notices. |
| Tre | `PARISH_TREASURER` | Parish Treasurer | PARISH | Maintains parish accounts and prepares monthly statements. |
| CPr | `COMMITTEE_PRESIDENT` | Committee President | ORG_UNIT | Leads an organisation unit; reviews its activities and minutes. |
| CSe | `COMMITTEE_SECRETARY` | Committee Secretary | ORG_UNIT | Records activities, meetings and minutes of an organisation unit. |
| CTr | `COMMITTEE_TREASURER` | Committee Treasurer | ORG_UNIT | Enters financial transactions of an organisation unit. |
| Anb | `ANBIYAM_LEADER` | Anbiyam Leader | ORG_UNIT | Leads an Anbiyam: its families, meetings and activities. |
| Sab | `SABAI_LEADER` | Sabai Leader | ORG_UNIT | Leads a Sabai / congregation. |
| Soc | `SOCIETY_LEADER` | Society Leader | ORG_UNIT | Leads a society or association. |
| Rev | `REVIEWER` | Reviewer | ANY | Generic reviewer used in workflows. |
| App | `APPROVER` | Approver | ANY | Generic approver used in workflows. |
| Mem | `GENERAL_MEMBER` | General Member | PARISH | Parishioner with a personal login. |
| Fam | `FAMILY_ACCOUNT` | Family Account User | PARISH | Family portal account (phase 2). |

Scope: **PARISH** = parish-wide only; **ORG_UNIT** = assigned for one organisation unit and applies only to that unit's records; **ANY** = either. Super Administrator and Diocese Administrator are platform roles (master database) and never exist inside a parish.

## Matrix

| Permission | Adm | Pri | Pre | Sec | Tre | CPr | CSe | CTr | Anb | Sab | Soc | Rev | App | Mem | Fam |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `user.view` — View user accounts | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `user.create` — Create user accounts | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `user.update` — Edit, activate, deactivate and unlock users | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `user.delete` — Delete (archive) user accounts | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `user.assign_role` — Assign and remove user roles | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `role.view` — View roles and permissions | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `role.manage` — Create, edit and delete roles | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `settings.view` — View parish settings | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |
| `settings.update` — Change parish settings | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `audit.view` — View the audit log | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `audit.export` — Export the audit log | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `org_unit.view` — View organisations (council, committees, Anbiyam, Sabai, societies) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `org_unit.create` — Create organisations | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `org_unit.update` — Edit organisations | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `org_unit.delete` — Archive organisations | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `org_unit.manage_members` — Manage members and office bearers | ✓ | ✓ |  |  |  | ✓ |  |  | ✓ | ✓ | ✓ |  |  |  |  |
| `family.view` — View families | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `family.create` — Register families | ✓ | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `family.update` — Edit families | ✓ | ✓ |  | ✓ |  |  |  |  | ✓ |  |  |  |  |  |  |
| `family.delete` — Archive families |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `family.transfer` — Transfer, merge and split families |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `family.export` — Export family registers | ✓ | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `member.view` — View members | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `member.view_sensitive` — View sensitive member details (DOB, contacts, sacraments) |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `member.create` — Add members | ✓ | ✓ |  | ✓ |  |  |  |  | ✓ |  |  |  |  |  |  |
| `member.update` — Edit members | ✓ | ✓ |  | ✓ |  |  |  |  | ✓ |  |  |  |  |  |  |
| `member.delete` — Archive members |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `member.export` — Export member registers | ✓ | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `sacrament.view` — View sacramental registers |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `sacrament.create` — Record sacramental entries |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `sacrament.update` — Edit sacramental entries |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `sacrament.export` — Export sacramental registers |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `priest.view` — View priests | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `priest.create` — Add priests | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `priest.update` — Edit priests and assignments | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `activity.view` — View activities | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| `activity.create` — Record activities |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `activity.update` — Edit activities |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `activity.delete` — Delete draft activities |  | ✓ |  | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `activity.submit` — Submit activities for approval |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `activity.review` — Review activities |  | ✓ | ✓ | ✓ |  | ✓ |  |  | ✓ | ✓ | ✓ | ✓ |  |  |  |
| `activity.approve` — Approve activities |  | ✓ |  |  |  |  |  |  |  |  |  |  | ✓ |  |  |
| `activity.reject` — Reject activities |  | ✓ |  |  |  |  |  |  |  |  |  |  | ✓ |  |  |
| `activity.export` — Export activities |  | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `meeting.view` — View meetings and minutes | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| `meeting.create` — Schedule meetings and record minutes |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `meeting.update` — Edit meetings and minutes |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `meeting.delete` — Cancel or delete draft meetings |  | ✓ |  | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `meeting.submit` — Submit minutes for approval |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `meeting.review` — Review minutes |  | ✓ | ✓ | ✓ |  | ✓ |  |  | ✓ | ✓ | ✓ | ✓ |  |  |  |
| `meeting.approve` — Approve minutes |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  | ✓ |  |  |
| `meeting.reject` — Reject minutes |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  | ✓ |  |  |
| `meeting.export` — Export meeting reports |  | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `action_item.view` — View action items | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `action_item.create` — Create action items |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `action_item.update` — Update action items |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |
| `workflow.view` — View workflow configuration | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |
| `workflow.manage` — Configure approval workflows | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `finance.view_summary` — View financial summaries |  | ✓ |  | ✓ | ✓ | ✓ |  | ✓ |  |  |  |  |  |  |  |
| `finance.view` — View financial transactions |  | ✓ | ✓ |  | ✓ |  |  | ✓ |  |  |  | ✓ | ✓ |  |  |
| `finance.create` — Enter financial transactions |  | ✓ |  |  | ✓ |  |  | ✓ |  |  |  |  |  |  |  |
| `finance.update` — Edit draft transactions |  | ✓ |  |  | ✓ |  |  | ✓ |  |  |  |  |  |  |  |
| `finance.delete` — Void draft transactions |  | ✓ |  |  | ✓ |  |  | ✓ |  |  |  |  |  |  |  |
| `finance.submit` — Submit transactions for approval |  | ✓ |  |  | ✓ |  |  | ✓ |  |  |  |  |  |  |  |
| `finance.review` — Review transactions |  | ✓ | ✓ |  | ✓ | ✓ |  |  |  |  |  | ✓ |  |  |  |
| `finance.approve` — Approve transactions |  | ✓ |  |  |  |  |  |  |  |  |  |  | ✓ |  |  |
| `finance.reject` — Reject transactions |  | ✓ |  |  | ✓ |  |  |  |  |  |  |  | ✓ |  |  |
| `finance.export` — Export financial reports |  | ✓ |  |  | ✓ |  |  |  |  |  |  |  |  |  |  |
| `finance_period.view` — View monthly periods and statements |  | ✓ | ✓ |  | ✓ |  |  |  |  |  |  |  | ✓ |  |  |
| `finance_period.submit` — Close a month and submit the statement |  | ✓ |  |  | ✓ |  |  |  |  |  |  |  |  |  |  |
| `finance_period.approve` — Approve monthly statements |  | ✓ |  |  |  |  |  |  |  |  |  |  | ✓ |  |  |
| `finance_period.release` — Release (publish and lock) monthly statements |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `notice.view` — View notices | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `notice.create` — Prepare notices |  | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `notice.update` — Edit notices |  | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `notice.delete` — Delete draft notices |  | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `notice.submit` — Submit notices for approval |  | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `notice.review` — Review notices |  | ✓ | ✓ | ✓ |  |  |  |  |  |  |  | ✓ |  |  |  |
| `notice.approve` — Approve notices |  | ✓ |  |  |  |  |  |  |  |  |  |  | ✓ |  |  |
| `notice.reject` — Reject notices |  | ✓ |  |  |  |  |  |  |  |  |  |  | ✓ |  |  |
| `notice.publish` — Publish and archive notices |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `document.view` — View documents | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| `document.view_confidential` — View confidential documents |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `document.create` — Upload documents | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `document.update` — Edit document metadata and versions | ✓ | ✓ |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |
| `document.delete` — Archive documents |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `document.export` — Download documents in bulk |  | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `report.view` — View reports | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |
| `report.export` — Export reports | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |  |  |
