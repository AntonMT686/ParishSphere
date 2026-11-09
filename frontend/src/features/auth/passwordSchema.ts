import { z } from 'zod';

export const PASSWORD_MIN = 10;

/** Client-side hint only; the backend policy is authoritative and its messages are shown on the field. */
export const newPasswordFields = {
  new_password: z.string().min(PASSWORD_MIN, `At least ${PASSWORD_MIN} characters`).max(256),
  confirm: z.string(),
};

export function withConfirm<T extends z.ZodRawShape>(shape: T, mismatch: string) {
  return z
    .object({ ...shape, ...newPasswordFields })
    .refine((v) => v.new_password === v.confirm, { path: ['confirm'], message: mismatch });
}
