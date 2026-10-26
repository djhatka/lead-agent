/*
  Skeleton: a grey shimmering placeholder shown while data loads, in the
  same size as the real thing, so the page doesn't jump when it arrives.

  <Skeleton className="h-8 w-24" />
*/
import clsx from 'clsx'

export function Skeleton({ className }) {
  return (
    <span
      aria-hidden
      className={clsx(
        'block animate-pulse rounded-control bg-surface-sunken motion-reduce:animate-none',
        className,
      )}
    />
  )
}

/** A few lines of placeholder text. */
export function SkeletonText({ lines = 3, className }) {
  return (
    <span className={clsx('flex flex-col gap-2', className)} role="status" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={clsx('h-3.5', i === lines - 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </span>
  )
}
