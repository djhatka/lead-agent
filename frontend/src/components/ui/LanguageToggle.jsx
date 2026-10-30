/*
  Task 39: English / Hindi switch. Same shape as ThemeToggle, but there
  are only two options, and the choice is saved on the business (so it's
  remembered next time anyone opens this business, not just this browser).
*/
import clsx from 'clsx'
import { motion } from 'motion/react'

import { spring } from '@/animations/presets'
import { useLanguage } from '@/hooks/useLanguage'
import { LANGUAGES } from '@/i18n/translations'

export function LanguageToggle({ className }) {
  const { lang, setLang, t } = useLanguage()

  function onKeyDown(event) {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
    if (!step) return
    event.preventDefault()
    const index = LANGUAGES.findIndex((o) => o.value === lang)
    const next = LANGUAGES[(index + step + LANGUAGES.length) % LANGUAGES.length]
    setLang(next.value)
    event.currentTarget.querySelector(`[data-value="${next.value}"]`)?.focus()
  }

  return (
    <div
      role="radiogroup"
      aria-label={t('common.language')}
      onKeyDown={onKeyDown}
      className={clsx('inline-flex rounded-full border border-line bg-surface-sunken p-1', className)}
    >
      {LANGUAGES.map(({ value, labelKey }) => {
        const active = lang === value
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={t(labelKey)}
            title={t(labelKey)}
            data-value={value}
            tabIndex={active ? 0 : -1}
            onClick={() => setLang(value)}
            className={clsx(
              'relative flex h-9 cursor-pointer items-center justify-center rounded-full px-3 text-xs font-semibold transition-colors duration-150',
              active ? 'text-ink' : 'text-ink-3 hover:text-ink',
            )}
          >
            {active && (
              <motion.span
                layoutId="language-toggle-highlight"
                transition={spring.snappy}
                className="absolute inset-0 rounded-full bg-surface-raised shadow-card"
              />
            )}
            <span className="relative">{value.toUpperCase()}</span>
          </button>
        )
      })}
    </div>
  )
}
