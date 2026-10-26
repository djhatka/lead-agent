/*
  Three-way switch: Light / System / Dark.
  The highlight slides between options (Motion `layoutId`).
  Works with the keyboard as a radio group: Tab to it, then arrow keys.
*/
import clsx from 'clsx'
import { Monitor, Moon, Sun } from 'lucide-react'
import { motion } from 'motion/react'

import { spring } from '@/animations/presets'
import { useTheme } from '@/hooks/useTheme'

const OPTIONS = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'system', label: 'System', icon: Monitor },
  { value: 'dark', label: 'Dark', icon: Moon },
]

export function ThemeToggle({ className }) {
  const { theme, setTheme } = useTheme()

  function onKeyDown(event) {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
    if (!step) return
    event.preventDefault()
    const index = OPTIONS.findIndex((o) => o.value === theme)
    const next = OPTIONS[(index + step + OPTIONS.length) % OPTIONS.length]
    setTheme(next.value)
    event.currentTarget.querySelector(`[data-value="${next.value}"]`)?.focus()
  }

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      onKeyDown={onKeyDown}
      className={clsx('inline-flex rounded-full border border-line bg-surface-sunken p-1', className)}
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = theme === value
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            data-value={value}
            tabIndex={active ? 0 : -1}
            onClick={() => setTheme(value)}
            className={clsx(
              'relative flex size-9 cursor-pointer items-center justify-center rounded-full transition-colors duration-150',
              active ? 'text-ink' : 'text-ink-3 hover:text-ink',
            )}
          >
            {active && (
              <motion.span
                layoutId="theme-toggle-highlight"
                transition={spring.snappy}
                className="absolute inset-0 rounded-full bg-surface-raised shadow-card"
              />
            )}
            <Icon aria-hidden className="relative size-4" />
          </button>
        )
      })}
    </div>
  )
}
