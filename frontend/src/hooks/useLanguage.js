/*
  Task 39: the dashboard's language ("en" | "hi"), and t(key) to read it.

  The business record is the source of truth (so it's remembered next time
  anyone opens this business, on any device). Before that's loaded - or
  before any business is chosen at all - we fall back to whatever this
  browser last used, kept in localStorage so the switch doesn't flicker
  back to English on every page load.

    const { lang, setLang, t } = useLanguage()
    <h1>{t('nav.home')}</h1>
    <p>{t('common.lastNDays', { n: 7 })}</p>
*/
// createElement, not JSX: this file is plain .js like every other hook here, and JSX
// syntax needs a .jsx file in this project's build setup.
import { createContext, createElement, useCallback, useContext, useMemo } from 'react'

import { translate } from '@/i18n/translations'
import { useBusiness } from '@/hooks/useBusiness'
import { useUpdateBusiness } from '@/hooks/useSettings'

const STORAGE_KEY = 'growth-partner-language'

function readStoredLang() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'hi' ? 'hi' : 'en'
  } catch {
    return 'en'
  }
}

function writeStoredLang(lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    // Not remembered in this browser, but still switched for this visit.
  }
}

const LanguageContext = createContext(null)

export function LanguageProvider({ children }) {
  const { business } = useBusiness()
  const updateBusiness = useUpdateBusiness()

  // The business's own setting wins once it's loaded; otherwise this browser's last choice.
  const lang = business?.language === 'hi' ? 'hi' : business ? 'en' : readStoredLang()

  const setLang = useCallback(
    (next) => {
      writeStoredLang(next)
      if (business && next !== business.language) {
        updateBusiness.mutate({ language: next })
      }
    },
    [business, updateBusiness],
  )

  const t = useCallback((key, vars) => translate(lang, key, vars), [lang])

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t])

  return createElement(LanguageContext.Provider, { value }, children)
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage() must be used inside <LanguageProvider>')
  return ctx
}
