/*
  When enquiries arrive: 24 thin columns, one per hour (India time).

  The 3 busiest hours are in the brand colour, the rest grey ("emphasis"),
  because the story is "be on the phone at these times". Every column can
  be hovered or Tab-focused for its exact count.
*/
import clsx from 'clsx'
import { motion } from 'motion/react'
import { useState } from 'react'

import { duration, ease } from '@/animations/presets'
import { hourLabel } from '@/styles/tokens'

export function HourColumns({ hours, busiest = [] }) {
  const [active, setActive] = useState(null)
  const top = Math.max(1, ...hours.map((h) => h.leads))
  const shown = active ?? hours.find((h) => h.hour === busiest.at(-1)) ?? null

  return (
    <div>
      <p className="mb-3 h-5 text-sm text-ink-2" aria-live="polite">
        {shown && (
          <>
            <span className="num font-semibold text-ink">{shown.leads}</span> leads between {hourLabel(shown.hour)} and{' '}
            {hourLabel((shown.hour + 1) % 24)}
          </>
        )}
      </p>
      <div className="flex h-36 items-end gap-[2px]" onPointerLeave={() => setActive(null)}>
        {hours.map((h, i) => {
          const hot = busiest.includes(h.hour)
          return (
            <button
              key={h.hour}
              type="button"
              aria-label={`${hourLabel(h.hour)}: ${h.leads} leads`}
              onPointerEnter={() => setActive(h)}
              onFocus={() => setActive(h)}
              onBlur={() => setActive(null)}
              className="group flex h-full flex-1 cursor-default items-end"
            >
              <motion.span
                className={clsx(
                  'block w-full rounded-t-[4px] transition-opacity group-hover:opacity-80 group-focus-visible:opacity-80',
                  h.leads === 0 && 'min-h-[2px]',
                )}
                style={{
                  height: `${(h.leads / top) * 100}%`,
                  backgroundColor: hot ? 'var(--brand)' : 'var(--line-strong)',
                  transformOrigin: 'bottom',
                }}
                initial={{ scaleY: 0 }}
                animate={{ scaleY: 1 }}
                transition={{ duration: duration.slow, ease: ease.out, delay: i * 0.015 }}
              />
            </button>
          )
        })}
      </div>
      <div className="mt-2 grid grid-cols-4 border-t border-axis pt-1.5 text-xs text-ink-3" aria-hidden>
        {[0, 6, 12, 18].map((h) => (
          <span key={h}>{hourLabel(h)}</span>
        ))}
      </div>
    </div>
  )
}
