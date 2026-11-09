import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import ta from './locales/ta.json';

export const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'ta', label: 'தமிழ்' },
] as const;

const LANG_KEY = 'ps.lang';

function initialLanguage(): string {
  try {
    return window.localStorage.getItem(LANG_KEY) ?? 'en';
  } catch {
    return 'en';
  }
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ta: { translation: ta } },
  lng: initialLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

i18n.on('languageChanged', (lng) => {
  try {
    window.localStorage.setItem(LANG_KEY, lng);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = lng;
});

export default i18n;
