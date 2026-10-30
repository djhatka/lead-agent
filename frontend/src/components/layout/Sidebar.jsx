/*
  The left menu on big screens: logo, the pages in groups, and the
  server status at the bottom.

  The highlight behind the active page slides from item to item (Motion
  `layoutId`). The chosen period (?days=) is kept when switching pages.
*/
import clsx from 'clsx'
import { Sparkles } from 'lucide-react'
import { motion } from 'motion/react'
import { NavLink, useSearchParams } from 'react-router'

import { spring } from '@/animations/presets'
import { NavCount } from '@/components/layout/NavBadges'
import { StatusFooter } from '@/components/layout/StatusFooter'
import { useLanguage } from '@/hooks/useLanguage'
import { useNavCounts } from '@/hooks/useNavCounts'
import { useFeatures } from '@/hooks/useFeatures'
import { NAV_GROUPS, visible } from '@/nav'

export function Logo() {
  const { t } = useLanguage()
  return (
    <div className="flex items-center gap-2.5 px-2">
      <span className="flex size-9 items-center justify-center rounded-control bg-brand text-on-brand shadow-sm">
        <Sparkles aria-hidden className="size-5" />
      </span>
      <div className="leading-tight">
        <p className="font-bold text-ink">Growth Partner</p>
        <p className="text-xs text-ink-3">{t('app.tagline')}</p>
      </div>
    </div>
  )
}

export function Sidebar() {
  const [params] = useSearchParams()
  const days = params.get('days')
  const search = days ? `?days=${days}` : ''
  const counts = useNavCounts()
  const { t } = useLanguage()

  const features = useFeatures()

  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-5 overflow-y-auto p-4">
      <div className="pt-1">
        <Logo />
      </div>

      {NAV_GROUPS.map((group) => (
        <div key={group.labelKey ?? 'main'}>
          {group.labelKey && <p className="px-3 pb-1.5 text-[11px] font-semibold tracking-wider text-ink-3 uppercase">{t(group.labelKey)}</p>}
          <ul className="flex flex-col gap-0.5">
            {visible(group.items, features.on).map(({ path, labelKey, icon: Icon, end, badge }) => (
              <li key={path}>
                <NavLink
                  to={{ pathname: path, search }}
                  end={end}
                  className={({ isActive }) =>
                    clsx(
                      'relative flex h-10 items-center gap-3 rounded-control px-3 text-sm font-medium transition-colors duration-150',
                      isActive ? 'text-brand' : 'text-ink-2 hover:bg-surface-sunken hover:text-ink',
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <motion.span layoutId="sidebar-active" transition={spring.snappy} className="absolute inset-0 rounded-control bg-brand-soft" />
                      )}
                      <Icon aria-hidden className="relative size-[18px] shrink-0" />
                      <span className="relative truncate">{t(labelKey)}</span>
                      {badge && <NavCount kind={badge} value={counts[badge]} className="relative ml-auto" />}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}

      <div className="mt-auto">
        <StatusFooter />
      </div>
    </nav>
  )
}
