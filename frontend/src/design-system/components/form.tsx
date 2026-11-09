import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Switch from '@mui/material/Switch';
import TextField, { type TextFieldProps } from '@mui/material/TextField';
import {
  Controller,
  type Control,
  type FieldValues,
  type Path,
  type UseFormSetError,
} from 'react-hook-form';
import { ApiError } from '@/api/client';

type BaseProps<T extends FieldValues> = { control: Control<T>; name: Path<T> };

/** Text field bound to react-hook-form; shows the field's validation or server error. */
export function FormTextField<T extends FieldValues>({ control, name, ...props }: BaseProps<T> & TextFieldProps) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <TextField
          {...props}
          {...field}
          value={field.value ?? ''}
          error={Boolean(fieldState.error)}
          helperText={fieldState.error?.message ?? props.helperText}
        />
      )}
    />
  );
}

export function FormSelect<T extends FieldValues>({
  control,
  name,
  options,
  ...props
}: BaseProps<T> & TextFieldProps & { options: { value: string; label: string }[] }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <TextField
          select
          {...props}
          {...field}
          value={field.value ?? ''}
          error={Boolean(fieldState.error)}
          helperText={fieldState.error?.message ?? props.helperText}
        >
          {options.map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
      )}
    />
  );
}

export function FormSwitch<T extends FieldValues>({ control, name, label }: BaseProps<T> & { label: string }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <FormControlLabel
          control={<Switch checked={Boolean(field.value)} onChange={(_, v) => field.onChange(v)} />}
          label={label}
        />
      )}
    />
  );
}

/**
 * Copy backend validation details onto form fields. Returns true when at least one field error was
 * applied (callers then skip the generic toast).
 */
export function applyServerErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly string[],
): boolean {
  if (!(error instanceof ApiError) || !error.details?.length) return false;
  let applied = false;
  for (const d of error.details) {
    if (fields.includes(d.field)) {
      setError(d.field as Path<T>, { type: 'server', message: d.message });
      applied = true;
    }
  }
  return applied;
}
