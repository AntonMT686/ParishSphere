import { subdomainFromHost } from './tenant';

describe('subdomainFromHost', () => {
  it.each([
    ['stmarys.parishsphere.app', 'stmarys'],
    ['stmarys.localhost', 'stmarys'],
    ['stmarys.parishsphere.localhost', 'stmarys'],
    ['localhost', null],
    ['parishsphere.app', null],
    ['www.parishsphere.app', null],
    ['127.0.0.1', null],
  ])('%s → %s', (host, expected) => {
    expect(subdomainFromHost(host)).toBe(expected);
  });
});
