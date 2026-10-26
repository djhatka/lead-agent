/*
  A counter next to a menu item: hot enquiries (amber, gently pulsing),
  unhappy reviews (red) or payments to confirm (green). Hidden at zero.
*/
import clsx from 'clsx'

const LABELS = { hot: 'hot enquiries waiting', reviews: 'unhappy reviews without a reply', payments: 'payments to confirm' }

export function NavCount({ kind, value, compact = false, className }) {
  if (!value) return null
  return (
    <span
      className={clsx(
        'num inline-flex items-center justify-center rounded-full font-semibold',
        compact ? 'h-[18px] min-w-[18px] px-1 text-[10px]' : 'h-5 min-w-5 px-1.5 text-xs',
        kind === 'hot' ? 'hot-pulse bg-accent text-white' : kind === 'payments' ? 'bg-good text-white' : 'bg-critical text-white',
        className,
      )}
      aria-label={`${value} ${LABELS[kind]}`}
    >
      {value > 99 ? '99+' : value}
    </span>
  )
}
