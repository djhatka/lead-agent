/*
  Light / dark / system theme.

  The choice is saved in the browser (localStorage) and applied by setting
  <html data-theme="light|dark">; every colour token in styles/index.css
  follows that attribute. "system" follows the device setting and updates
  live if the device switches (e.g. at sunset).

  A tiny script in index.html applies the saved theme before React even
  starts, so the page never flashes white in dark mode.

  Usage:  const { theme, resolved, setTheme } = useTheme()
*/
import { useCallback, useSyncExternalStore } from 'react'

const STORAGE_KEY = 'lead-intel-theme'
const media = window.matchMedia('(prefers-color-scheme: dark)')
const listeners = new Set()

function readChoice() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  } catch {
    return 'system' // private mode or blocked storage: just follow the device
  }
}

let choice = readChoice()

function resolve(value) {
  return value === 'system' ? (media.matches ? 'dark' : 'light') : value
}

function apply() {
  document.documentElement.dataset.theme = resolve(choice)
  listeners.forEach((notify) => notify())
}

media.addEventListener('change', () => {
  if (choice === 'system') apply()
})

function subscribe(notify) {
  listeners.add(notify)
  return () => listeners.delete(notify)
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, () => choice)
  const resolved = resolve(theme)

  const setTheme = useCallback((next) => {
    choice = next
    try {
      if (next === 'system') localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Not saved, but still applied for this visit.
    }
    apply()
  }, [])

  return { theme, resolved, setTheme }
}
