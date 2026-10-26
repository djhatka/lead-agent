/*
  The phone's bottom bar: Home, Enquiries, Content, Reviews, and "More"
  (a sheet with the other pages, the theme switch and server status).

  Big thumb-sized targets (64px tall), labels under every icon, and room
  for the phone's home indicator (safe-area inset).
*/
import clsx from 'clsx'
import { Ellipsis, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router'

import { fadeIn, spring } from '@/animations/presets'
import { NavCount } from '@/components/layout/NavBadges'
import { StatusFooter } from '@/components/layout/StatusFooter'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { useLockScroll } from '@/hooks/useLockScroll'
import { useNavCounts } from '@/hooks/useNavCounts'
import { BOTTOM_NAV, NAV } from '@/nav'

const MORE = NAV.filter((item) => !BOTTOM_NAV.some((b) => b.path === item.path))

function MoreSheet({ onClose }) {
  const { pathname } = useLocation()
  useLockScroll()

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <>
      <motion.div variants={fadeIn} initial="hidden" animate="show" exit="exit" onClick={onClose} className="fixed inset-0 z-40 bg-black/40 lg:hidden" />
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="More pages"
        initial={{ y: '100%' }}
        animate={{ y: 0, transition: spring.gentle }}
        exit={{ y: '100%', transition: { duration: 0.2 } }}
        className="fixed inset-x-0 bottom-0 z-50 max-h-[85dvh] overflow-y-auto rounded-t-3xl bg-surface p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-pop lg:hidden"
      >
        <div className="mb-3 flex items-center justify-between">
          <p className="text-base font-semibold text-ink">More</p>
          <button
            type="button"
            autoFocus
            onClick={onClose}
            aria-label="Close"
            className="flex size-11 cursor-pointer items-center justify-center rounded-control text-ink-2 hover:bg-surface-sunken"
          >
            <X aria-hidden className="size-5" />
          </button>
        </div>
        <ul className="grid grid-cols-2 gap-2">
          {MORE.map(({ path, label, short, icon: Icon }) => {
            const active = pathname === path
            return (
              <li key={path}>
                <Link
                  to={path}
                  onClick={onClose}
                  aria-current={active ? 'page' : undefined}
                  className={clsx(
                    'flex h-full min-h-20 flex-col justify-between gap-2 rounded-card border p-3 text-sm font-medium transition-colors',
                    active ? 'border-brand/40 bg-brand-soft text-brand' : 'border-line bg-surface-raised text-ink hover:border-line-strong',
                  )}
                >
                  <Icon aria-hidden className="size-5" />
                  {short ?? label}
                </Link>
              </li>
            )
          })}
        </ul>
        <div className="mt-4 flex items-center justify-between rounded-card border border-line bg-surface-raised p-3">
          <span className="text-sm font-medium text-ink">Theme</span>
          <ThemeToggle />
        </div>
        <div className="mt-3">
          <StatusFooter />
        </div>
      </motion.div>
    </>
  )
}

export function BottomNav() {
  const { pathname } = useLocation()
  const counts = useNavCounts()
  // The sheet remembers the page it was opened on, so changing page closes it.
  const [openedOn, setOpenedOn] = useState(null)
  const moreOpen = openedOn === pathname
  const moreActive = MORE.some((item) => item.path === pathname)

  const item = 'relative flex flex-1 cursor-pointer flex-col items-center justify-center gap-1 text-[11px] font-medium'

  return (
    <>
      <nav
        aria-label="Main"
        className="glass fixed inset-x-0 bottom-0 z-30 rounded-none border-x-0 border-b-0 pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        <ul className="flex h-16">
          {BOTTOM_NAV.map(({ path, label, icon: Icon, badge, match }) => {
            const active = match(pathname)
            return (
              <li key={path} className="flex flex-1">
                <Link to={path} aria-current={active ? 'page' : undefined} className={clsx(item, active ? 'text-brand' : 'text-ink-3')}>
                  <span className="relative flex h-8 w-14 items-center justify-center">
                    {active && <motion.span layoutId="bottom-active" transition={spring.snappy} className="absolute inset-0 rounded-full bg-brand-soft" />}
                    <Icon aria-hidden className="relative size-5" />
                    {badge && <NavCount kind={badge} value={counts[badge]} compact className="absolute -top-1 right-1.5" />}
                  </span>
                  {label}
                </Link>
              </li>
            )
          })}
          <li className="flex flex-1">
            <button
              type="button"
              aria-expanded={moreOpen}
              onClick={() => setOpenedOn(pathname)}
              className={clsx(item, moreActive ? 'text-brand' : 'text-ink-3')}
            >
              <span className="relative flex h-8 w-14 items-center justify-center">
                {moreActive && <motion.span layoutId="bottom-active" transition={spring.snappy} className="absolute inset-0 rounded-full bg-brand-soft" />}
                <Ellipsis aria-hidden className="relative size-5" />
              </span>
              More
            </button>
          </li>
        </ul>
      </nav>
      <AnimatePresence>{moreOpen && <MoreSheet onClose={() => setOpenedOn(null)} />}</AnimatePresence>
    </>
  )
}
