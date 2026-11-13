import { expect, type Browser, type Page } from '@playwright/test';

export const PASSWORD = process.env.E2E_PASSWORD ?? 'ChangeMe-Now1';

/** A signed-in page for a demo user (one browser context per user, like separate devices). */
export async function signIn(browser: Browser, username: string): Promise<Page> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on('pageerror', (e) => { throw new Error(`${username}: page error: ${e.message}`); });
  await page.goto('/login');
  await page.getByLabel('Username or email').fill(username);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: /Welcome to/ })).toBeVisible();
  return page;
}

/** Open an item in My Approvals by its title and take a decision. */
export async function decide(page: Page, title: string | RegExp, action: 'Approve' | 'Return for rework' = 'Approve') {
  await page.goto('/approvals');
  await page.getByText(title).first().click();
  await page.waitForURL(/\/approvals\/[0-9A-Z]{26}$/);
  await page.getByRole('button', { name: action, exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: action === 'Approve' ? 'Approved' : 'Returned' }).first()).toBeVisible();
}

/** Approve everything waiting with this user (bulk action in My Approvals). */
export async function approveAll(page: Page) {
  await page.goto('/approvals');
  await expect(page.getByText(/waiting · \d+ overdue/)).toBeVisible();
  await page.waitForLoadState('networkidle');
  if (await page.getByText('Nothing is waiting for you').count()) return;
  await page.getByRole('checkbox', { name: 'Select all rows' }).check();
  await page.getByRole('button', { name: /^Approve \d+ selected$/ }).click();
  await expect(page.getByText(/records? approved/)).toBeVisible();
}

export async function pick(page: Page, label: string | RegExp, option: string | RegExp, scope?: Page | ReturnType<Page['locator']>) {
  await (scope ?? page).getByLabel(label).first().click();
  await page.getByRole('option', { name: option }).first().click();
}
