/*
  Where toasts appear (see toast.js for how to show one). Mounted once in
  the app shell. Screen readers hear each message (aria-live). They drop in
  at the top centre, so they never cover a drawer's buttons or the bottom bar.
*/
import clsx from 'clsx'
import { CircleCheck, Flame, Info, TriangleAlert, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useSyncExternalStore } from 'react'
import { Link } from 'react-router'

import { spring } from '@/animations/presets'
import { dismiss, toastStore } from '@/components/ui/toast'

const TONES = {
  neutral: { icon: Info, className: 'text-brand' },
  good: { icon: CircleCheck, className: 'text-good-ink' },
  accent: { icon: Flame, className: 'text-accent-ink' },
  critical: { icon: TriangleAlert, className: 'text-critical-ink' },
}

export function Toaster() {
  const list = useSyncExternalStore(toastStore.subscribe, toastStore.snapshot)

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-4 top-3 z-[60] flex flex-col items-center gap-2"
    >
      <AnimatePresence initial={false}>
        {list.map((t) => {
          const tone = TONES[t.tone] ?? TONES.neutral
          const Icon = tone.icon
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: -16, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1, transition: spring.gentle }}
              exit={{ opacity: 0, scale: 0.96, transition: { duration: 0.15 } }}
              className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-card border border-line bg-surface-raised p-3.5 shadow-pop"
            >
              <Icon aria-hidden className={clsx('mt-0.5 size-5 shrink-0', tone.className)} />
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-semibold text-ink">{t.title}</p>
                {t.body && <p className="mt-0.5 text-ink-2">{t.body}</p>}
                {t.to && (
                  <Link to={t.to} onClick={() => dismiss(t.id)} className="mt-1.5 inline-block font-semibold text-brand hover:underline">
                    {t.action ?? 'Open'}
                  </Link>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss"
                className="-m-1 flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-control text-ink-3 hover:bg-surface-sunken hover:text-ink"
              >
                <X aria-hidden className="size-4" />
              </button>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
