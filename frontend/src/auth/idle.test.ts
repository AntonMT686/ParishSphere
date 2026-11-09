import { computeIdle } from './idle';

describe('computeIdle', () => {
  const t0 = 1_000_000;
  it('is quiet before the warning window', () => {
    expect(computeIdle(t0 + 60_000, t0, 1800)).toEqual({ remaining: 1740, warning: false, expired: false });
  });
  it('warns during the last two minutes', () => {
    expect(computeIdle(t0 + 1700_000, t0, 1800)).toEqual({ remaining: 100, warning: true, expired: false });
  });
  it('expires at the limit', () => {
    expect(computeIdle(t0 + 1800_000, t0, 1800)).toEqual({ remaining: 0, warning: false, expired: true });
  });
});
