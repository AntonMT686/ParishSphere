import { ApiError } from '@/api/client';
import { applyServerErrors } from './form';

describe('applyServerErrors', () => {
  it('maps backend field errors onto the form', () => {
    const setError = vi.fn();
    const err = new ApiError(422, 'WEAK_PASSWORD', 'weak', [
      { field: 'new_password', message: 'Is too common' },
      { field: 'unknown', message: 'x' },
    ]);
    expect(applyServerErrors(err, setError, ['new_password'])).toBe(true);
    expect(setError).toHaveBeenCalledWith('new_password', { type: 'server', message: 'Is too common' });
    expect(setError).toHaveBeenCalledTimes(1);
    expect(applyServerErrors(new Error('x'), setError, ['a'])).toBe(false);
  });
});
