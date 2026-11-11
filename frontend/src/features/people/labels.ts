import { useTranslation } from 'react-i18next';

export const RELATIONSHIPS = [
  'HEAD', 'SPOUSE', 'SON', 'DAUGHTER', 'FATHER', 'MOTHER', 'BROTHER', 'SISTER', 'GRANDSON', 'GRANDDAUGHTER',
  'SON_IN_LAW', 'DAUGHTER_IN_LAW', 'FATHER_IN_LAW', 'MOTHER_IN_LAW', 'GRANDFATHER', 'GRANDMOTHER', 'NEPHEW', 'NIECE',
  'OTHER_RELATIVE', 'OTHER',
] as const;
export type Relationship = (typeof RELATIONSHIPS)[number];
export const GENDERS = ['M', 'F', 'O'] as const;
export const MARITAL = ['SINGLE', 'MARRIED', 'WIDOWED', 'SEPARATED', 'RELIGIOUS'] as const;

export function useLabels() {
  const { t } = useTranslation();
  return {
    rel: (r: string) => t(`people.rel.${r}`, { defaultValue: r.replace(/_/g, ' ').toLowerCase() }),
    gender: (g: string) => t(`people.gender.${g}`, { defaultValue: g }),
    marital: (m: string) => t(`people.marital.${m}`, { defaultValue: m.toLowerCase() }),
    event: (e: string) => t(`people.event.${e}`, { defaultValue: e.replace(/_/g, ' ').toLowerCase() }),
  };
}
