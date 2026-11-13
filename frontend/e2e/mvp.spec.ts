import { expect, test, type Page } from '@playwright/test';
import { approveAll, pick, signIn } from './helpers';

/**
 * The MVP demo journey (docs/09-roadmap-and-testing.md §3) on the demo parish created by
 * `ps-admin seed-demo`. Steps depend on each other, so they run in order on one fresh database.
 */
test.describe.configure({ mode: 'serial' });

const today = new Date();
const lastMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1);
const LAST_KEY = `${lastMonth.getFullYear()}-${String(lastMonth.getMonth() + 1).padStart(2, '0')}`;
const LAST_LABEL = lastMonth.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
const stamp = Date.now().toString().slice(-5);

let priest: Page;

/** Approve the first item in My Approvals whose title matches; false when there is none. */
async function approveIfWaiting(page: Page, title: RegExp): Promise<boolean> {
  await page.goto('/approvals');
  await expect(page.getByText(/waiting · \d+ overdue/)).toBeVisible();
  await page.waitForLoadState('networkidle');
  const item = page.getByText(title).first();
  if (!(await item.count())) return false;
  await item.click();
  await page.waitForURL(/\/approvals\/[0-9A-Z]{26}$/);
  await page.getByRole('button', { name: 'Approve', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Approved' }).first()).toBeVisible();
  return true;
}

test('Parish Priest dashboard shows real numbers and pending approvals', async ({ browser }) => {
  priest = await signIn(browser, 'frjoseph');
  await expect(priest.getByText('Families', { exact: true }).first()).toBeVisible();
  await expect(priest.getByText(/^\d{2,}$/).first()).toBeVisible(); // live counts, not placeholders
  await expect(priest.getByRole('list', { name: 'My approvals' })).toContainText('Church roof repair');
  await expect(priest.getByRole('table', { name: 'Income vs expense' })).toBeAttached(); // chart with data table
  await expect(priest.getByText('Fr. Joseph Antony').or(priest.getByText('Rev. Fr. Joseph Antony')).first()).toBeVisible();
});

test('Secretary registers a family with members in an Anbiyam', async ({ browser }) => {
  const mary = await signIn(browser, 'mary');
  const name = `Rayan ${stamp}`;
  await mary.goto('/families/new');
  await mary.locator('input[name="family_name"]').fill(name);
  await mary.locator('input[name="phone"]').fill(`+91 9876${stamp}1`);
  await mary.getByRole('button', { name: 'Next' }).click();
  await mary.locator('input[name="address_line1"]').fill('7 Luz Church Road');
  await mary.locator('input[name="city"]').fill('Chennai');
  await mary.getByRole('button', { name: 'Next' }).click();
  const members: [string, string, string | null][] = [['Daniel', 'Male', null], ['Sophia', 'Female', 'Spouse']];
  for (let i = 0; i < members.length; i++) {
    const [first, gender, rel] = members[i]!;
    if (i > 0) await mary.getByRole('button', { name: 'Add member' }).click();
    await mary.locator(`input[name="members.${i}.first_name"]`).fill(first);
    const card = mary.locator('form .MuiCardContent-root .MuiCard-root').nth(i);
    await pick(mary, /Gender/, gender, card);
    if (rel) await pick(mary, /Relationship to head/, rel, card);
  }
  await mary.getByRole('button', { name: 'Next' }).click();
  const anb = mary.getByLabel('Anbiyam').first();
  await anb.click();
  await anb.fill('Anne');
  await mary.getByRole('option', { name: /St. Anne Anbiyam/ }).first().click();
  await expect(mary.getByText('No similar families found.')).toBeVisible();
  await mary.getByRole('button', { name: 'Register family' }).click();
  await mary.waitForURL(/\/families\/[0-9A-Z]{26}$/);
  await expect(mary.getByRole('heading', { name })).toBeVisible();
  await expect(mary.getByText('St. Anne Anbiyam').first()).toBeVisible();
  await expect(mary.getByText('Sophia')).toBeVisible();
});

test('Youth Society secretary records an activity; society President, Parish Secretary and Priest approve it', async ({ browser }) => {
  const kevin = await signIn(browser, 'kevin');
  const title = `Bible quiz ${stamp}`;
  await kevin.goto('/activities/new');
  await kevin.getByLabel(/Activity name/).fill(title);
  await expect(kevin.getByLabel('Organisation').filter({ hasText: 'Youth Society' })).toBeVisible();
  await pick(kevin, 'Category', 'Spiritual');
  await kevin.getByLabel('Location').fill('Parish hall');
  await kevin.getByLabel('Planned programme').fill('Quiz in three rounds for the Anbiyam teams');
  await kevin.getByRole('button', { name: 'Save draft' }).click();
  await kevin.waitForURL(/\/activities\/[0-9A-Z]{26}$/);
  const url = kevin.url();
  await kevin.getByRole('button', { name: 'Submit for approval' }).click();
  await kevin.getByRole('dialog').getByRole('button', { name: 'Send for approval' }).click();
  await expect(kevin.getByText(/waiting for approval and cannot be changed/)).toBeVisible();

  const approvers = { jerome: await signIn(browser, 'jerome'), mary: await signIn(browser, 'mary'), frjoseph: priest };
  const re = new RegExp(title);
  for (let round = 0; round < 4; round++) {
    let acted = false;
    for (const page of Object.values(approvers)) acted = (await approveIfWaiting(page, re)) || acted;
    if (!acted) break;
  }
  await kevin.goto(url);
  await expect(kevin.getByText('Approved').first()).toBeVisible();
  const timeline = kevin.getByRole('list', { name: 'Stages' });
  await expect(timeline).toContainText('Parish Priest');
});

test('Parish Priest approves the roof repair the Treasurer reviewed', async () => {
  expect(await approveIfWaiting(priest, /Church roof repair/)).toBe(true);
  await priest.goto('/finance/transactions');
  const row = priest.getByRole('row').filter({ hasText: 'Church roof repair' });
  await expect(row.getByText('Approved')).toBeVisible();
});

test('Month closed by the Treasurer is approved and released with a PDF statement', async ({ browser }) => {
  expect(await approveIfWaiting(priest, new RegExp(LAST_LABEL))).toBe(true);
  await priest.goto(`/finance/statements/${LAST_KEY}`);
  await expect(priest.getByText('Version 1').first()).toBeVisible();
  const [pdf] = await Promise.all([priest.waitForEvent('download'), priest.getByRole('button', { name: 'PDF', exact: true }).first().click()]);
  expect(pdf.suggestedFilename()).toMatch(/\.pdf$/);
  await priest.getByRole('button', { name: 'Release statement' }).click();
  await priest.getByRole('button', { name: 'Confirm' }).click();
  await expect(priest.getByText('Statement released')).toBeVisible();
  const thomas = await signIn(browser, 'thomas');
  await thomas.goto('/finance/statements');
  await expect(thomas.getByText("You don't have access to this page")).toBeVisible(); // parishioners never see the books
});

test('Weekly notice is approved and published to parishioners', async ({ browser }) => {
  const mary = await signIn(browser, 'mary');
  const title = `Weekly notice ${stamp}`;
  await mary.goto('/notices/new');
  await mary.getByLabel(/^Title\s*\*$/).fill(title);
  await mary.getByLabel(/^Notice\s*\*$/).fill('Holy Hour on Thursday at 6 pm. Choir practice on Saturday.');
  await mary.getByRole('button', { name: 'Save draft' }).click();
  await mary.waitForURL(/\/notices\/[0-9A-Z]{26}$/);
  await mary.getByRole('button', { name: 'Submit for approval' }).click();
  await expect(mary.getByText('In review').first()).toBeVisible();
  await approveAll(await signIn(browser, 'raj'));
  expect(await approveIfWaiting(priest, new RegExp(title))).toBe(true);
  const thomas = await signIn(browser, 'thomas');
  await thomas.goto('/notices');
  await expect(thomas.getByRole('article', { name: title })).toBeVisible();
});

test('Parishioner sees their family, donations and events', async ({ browser }) => {
  const thomas = await signIn(browser, 'thomas');
  await expect(thomas.getByText('My family', { exact: true })).toBeVisible();
  await expect(thomas.getByText(/Fernando/).first()).toBeVisible();
  await expect(thomas.getByRole('list', { name: 'Upcoming events' })).toContainText('Parish feast novena');
});

test('Global search and report export', async () => {
  await priest.goto('/');
  await expect(priest.getByRole('heading', { name: /Welcome to/ })).toBeVisible();
  await priest.keyboard.press('Control+k');
  await expect(priest.getByRole('combobox', { name: 'Search…' })).toBeFocused();
  await priest.keyboard.type('Fernando');
  await expect(priest.getByRole('listbox', { name: 'Search results' }).getByRole('group', { name: 'Families' })).toBeVisible();
  await priest.keyboard.press('ArrowDown');
  await priest.keyboard.press('Enter');
  await priest.waitForURL(/\/families\/[0-9A-Z]{26}/);
  await priest.goto('/reports/donation_report');
  await expect(priest.getByRole('table', { name: 'Donation report' })).toBeVisible();
  await priest.getByRole('button', { name: 'Export' }).click();
  const [xlsx] = await Promise.all([priest.waitForEvent('download'), priest.getByRole('menuitem', { name: 'Excel (.xlsx)' }).click()]);
  expect(xlsx.suggestedFilename()).toMatch(/\.xlsx$/);
});

test('Audit log shows the journey', async ({ browser }) => {
  const admin = await signIn(browser, 'admin');
  await admin.goto('/admin/audit');
  await admin.getByLabel('Search…', { exact: false }).first().fill('frjoseph');
  await expect(admin.getByRole('grid').getByText('frjoseph').first()).toBeVisible();
  await admin.getByRole('combobox', { name: 'Action' }).click();
  await admin.getByRole('option', { name: 'REPORT_EXPORTED' }).click();
  await expect(admin.getByRole('grid').getByText('report · donation_report').first()).toBeVisible();
});

test('Signing out ends the session', async () => {
  await priest.goto('/');
  await priest.getByRole('button', { name: 'My profile' }).click();
  await priest.getByRole('menuitem', { name: 'Sign out' }).click();
  await expect(priest.getByRole('button', { name: 'Sign in' })).toBeVisible();
  await priest.goto('/finance/transactions');
  await expect(priest.getByRole('button', { name: 'Sign in' })).toBeVisible();
});
