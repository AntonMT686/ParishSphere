import Autocomplete from '@mui/material/Autocomplete';
import TextField from '@mui/material/TextField';
import { useDeferredValue, useState } from 'react';
import type { FamilyListItem, Member } from '@/api/types';
import { useFamilySearch, useMemberSearch } from './api';

export function FamilyPicker({ label, value, onChange, excludeId }: {
  label: string;
  value: FamilyListItem | null;
  onChange: (f: FamilyListItem | null) => void;
  excludeId?: string;
}) {
  const [input, setInput] = useState('');
  const q = useDeferredValue(input);
  const { data = [], isFetching } = useFamilySearch(q);
  return (
    <Autocomplete
      value={value}
      options={data.filter((f) => f.id !== excludeId && !['MERGED', 'TRANSFERRED_OUT'].includes(f.status))}
      loading={isFetching}
      filterOptions={(x) => x}
      getOptionLabel={(f) => `${f.family_name} · ${f.code}${f.head_name ? ` · ${f.head_name}` : ''}`}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      onInputChange={(_, v) => setInput(v)}
      onChange={(_, v) => onChange(v)}
      renderInput={(p) => <TextField {...p} label={label} />}
    />
  );
}

export function MemberPicker({ label, value, onChange }: {
  label: string;
  value: Member | null;
  onChange: (m: Member | null) => void;
}) {
  const [input, setInput] = useState('');
  const q = useDeferredValue(input);
  const { data = [], isFetching } = useMemberSearch(q);
  return (
    <Autocomplete
      value={value}
      options={data}
      loading={isFetching}
      filterOptions={(x) => x}
      getOptionLabel={(m) => `${m.full_name} · ${m.code} · ${m.family.name}${m.age !== null ? ` · ${m.age}` : ''}`}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      onInputChange={(_, v) => setInput(v)}
      onChange={(_, v) => onChange(v)}
      renderInput={(p) => <TextField {...p} label={label} />}
    />
  );
}
