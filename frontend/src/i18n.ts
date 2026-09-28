import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en/translation.json'
import hi from './locales/hi/translation.json'
import mr from './locales/mr/translation.json'

const storedLanguage = localStorage.getItem('mahaclear_language')

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi }, mr: { translation: mr } },
  lng: storedLanguage && ['en', 'hi', 'mr'].includes(storedLanguage) ? storedLanguage : 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
  returnNull: false,
})

i18n.on('languageChanged', (language) => localStorage.setItem('mahaclear_language', language))

export default i18n
