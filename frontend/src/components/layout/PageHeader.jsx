/*
  The top of every page: its title, one line saying what it's for, the
  7/30/90-day switch (on pages that use it) and the page's main buttons.

  <PageHeader actions={<Button variant="primary">Plan my week</Button>} />

  Title, subtitle and the period switch come from the route's `handle`
  in routes.jsx unless passed in.
*/
import clsx from 'clsx'
import { motion } from 'motion/react'

import { spring } from '@/animations/presets'
import { PERIODS, usePeriod } from '@/hooks/usePeriod'
import { useRouteHandle } from '@/hooks/useRouteHandle'

export function PeriodSwitch() {
  const { days, setDays } = usePeriod()
  return (
    <div role="radiogroup" aria-label="Time period" className="inline-flex rounded-full border border-line bg-surface-sunken p-1">
      {PERIODS.map((value) => {
        const active = value === days
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={`Last ${value} days`}
            onClick={() => setDays(value)}
            className={clsx(
              'relative h-9 cursor-pointer rounded-full px-3.5 text-sm font-medium transition-colors duration-150',
              active ? 'text-ink' : 'text-ink-3 hover:text-ink',
            )}
          >
            {active && <motion.span layoutId="period-highlight" transition={spring.snappy} className="absolute inset-0 rounded-full bg-surface-raised shadow-card" />}
            <span className="num relative">{value} days</span>
          </button>
        )
      })}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions, className }) {
  const handle = useRouteHandle()
  const sub = subtitle ?? handle.subtitle
  return (
    <div className={clsx('mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-4', className)}>
      <div className="min-w-0">
        <h1 className="text-2xl font-bold tracking-tight sm:text-[1.75rem]">{title ?? handle.title}</h1>
        {sub && <p className="mt-1 text-sm text-ink-3 sm:text-base">{sub}</p>}
      </div>
      {(actions || handle.period) && (
        <div className="flex flex-wrap items-center gap-2">
          {actions}
          {handle.period && <PeriodSwitch />}
        </div>
      )}
    </div>
  )
}
