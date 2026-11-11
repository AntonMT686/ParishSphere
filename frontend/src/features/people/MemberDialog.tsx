import { zodResolver } from '@hookform/resolvers/zod';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { api } from '@/api/client';
import type { Member } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { applyServerErrors, useFeedback } from '@/design-system';
import { peopleKeys } from './api';
import { emptyMember, MEMBER_FIELDS, MemberFormFields, memberSchema, toApi, type MemberValues } from './memberForm';

function fromMember(m: Member): MemberValues {
  const v = emptyMember(m.relationship_to_head as MemberValues['relationship_to_head']);
  for (const k of MEMBER_FIELDS) {
    const val = (m as unknown as Record<string, unknown>)[k];
    (v as unknown as Record<string, unknown>)[k] = val ?? '';
  }
  return v;
}

/** Add a member to a family (familyId) or edit an existing member (member). */
export function MemberDialog({ open, onClose, familyId, member }: {
  open: boolean;
  onClose: () => void;
  familyId?: string;
  member?: Member;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const can = useCan();
  const { toast, toastError } = useFeedback();
  // Personal details may be entered when adding; editing them later needs member.view_sensitive.
  const sensitive = member ? member.sensitive_visible : true;
  const sacraments = member ? member.sacraments_visible && can('sacrament.update') : can('sacrament.update');
  const { control, handleSubmit, reset, setError } = useForm<MemberValues>({ resolver: zodResolver(memberSchema) });
  useEffect(() => {
    if (open) reset(member ? fromMember(member) : emptyMember('SON'));
  }, [open, member, reset]);
  const save = useMutation({
    mutationFn: async (v: MemberValues) => {
      const body = toApi(v, { sensitive, sacraments });
      if (member) {
        if (member.is_head) delete body.relationship_to_head;
        return (await api.patch<Member>(`/members/${member.id}`, body)).data;
      }
      return (await api.post<Member>(`/families/${familyId}/members`, body)).data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: peopleKeys.families });
      void qc.invalidateQueries({ queryKey: peopleKeys.members });
      toast(t('common.saved'));
      onClose();
    },
    onError: (e) => {
      if (!applyServerErrors(e, setError, MEMBER_FIELDS)) toastError(e);
    },
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <form noValidate onSubmit={handleSubmit((v) => save.mutate(v))}>
        <DialogTitle>{member ? `${t('common.edit')}: ${member.full_name}` : t('people.addMember')}</DialogTitle>
        <DialogContent>
          <div style={{ paddingTop: 8 }}>
            <MemberFormFields control={control} base="" sensitive={sensitive} sacraments={sacraments} headLocked={member?.is_head} />
          </div>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" variant="contained" disabled={save.isPending}>{member ? t('common.save') : t('common.create')}</Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
