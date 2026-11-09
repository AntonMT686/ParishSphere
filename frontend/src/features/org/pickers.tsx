import Autocomplete from '@mui/material/Autocomplete';
import TextField from '@mui/material/TextField';
import { useDeferredValue, useState } from 'react';
import type { OrgUnit, UserLookup } from '@/api/types';
import { useUnitSearch, useUserLookup } from './api';

export function UserPicker({ label, value, onChange }: {
  label: string;
  value: UserLookup | null;
  onChange: (u: UserLookup | null) => void;
}) {
  const [input, setInput] = useState('');
  const q = useDeferredValue(input);
  const { data = [], isFetching } = useUserLookup(q);
  return (
    <Autocomplete
      value={value}
      options={data}
      loading={isFetching}
      filterOptions={(x) => x}
      getOptionLabel={(u) => `${u.full_name} (@${u.username})`}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      onInputChange={(_, v) => setInput(v)}
      onChange={(_, v) => onChange(v)}
      renderInput={(p) => <TextField {...p} label={label} />}
    />
  );
}

export function OrgUnitPicker({ label, value, onChange, type, excludeId }: {
  label: string;
  value: Pick<OrgUnit, 'id' | 'name' | 'code'> | null;
  onChange: (u: Pick<OrgUnit, 'id' | 'name' | 'code'> | null) => void;
  type?: string;
  excludeId?: string;
}) {
  const [input, setInput] = useState('');
  const q = useDeferredValue(input);
  const { data = [], isFetching } = useUnitSearch(q, type);
  return (
    <Autocomplete
      value={value}
      options={data.filter((u) => u.id !== excludeId)}
      loading={isFetching}
      filterOptions={(x) => x}
      getOptionLabel={(u) => `${u.name} (${u.code})`}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      onInputChange={(_, v) => setInput(v)}
      onChange={(_, v) => onChange(v)}
      renderInput={(p) => <TextField {...p} label={label} />}
    />
  );
}
