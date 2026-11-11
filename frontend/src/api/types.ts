/** Convenience aliases over the generated OpenAPI types (`npm run gen:api`). */
import type { components } from './schema';

type S = components['schemas'];

export type Me = S['MeOut'];
export type TokenOut = S['AuthTokenOut'];
export type SessionOut = S['SessionOut'];
export type UserOut = S['UserOut'];
export type UserCreate = S['UserCreate'];
export type UserUpdate = S['UserUpdate'];
export type AssignmentOut = S['AssignmentOut'];
export type AssignmentCreate = S['AssignmentCreate'];
export type RoleSummary = S['RoleSummaryOut'];
export type Role = S['RoleOut'];
export type PermissionModule = S['PermissionModuleOut'];
export type AuditLog = S['AuditLogOut'];
export type NotificationItem = S['NotificationOut'];
export type NotificationPreference = S['PreferenceOut'];
export type OrgUnitType = S['TypeOut'];
export type OrgPosition = S['PositionOut'];
export type OrgUnit = S['UnitOut'];
export type OfficeBearer = S['BearerOut'];
export type UserLookup = S['UserLookupOut'];
export type FamilyListItem = S['FamilyListOut'];
export type Family = S['FamilyOut'];
export type FamilyCreate = S['FamilyCreate'];
export type Member = S['MemberOut'];
export type MemberIn = S['MemberIn'];
export type DuplicateCandidate = S['DuplicateOut'];
export type FamilyHistory = S['FamilyHistoryOut'];
export type Membership = S['MembershipOut'];
export type Ref = S['Ref'];
