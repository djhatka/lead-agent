/*
  Button, in four looks:
    primary    the main action on a screen (one per screen)
    secondary  everything else
    ghost      quiet actions inside cards and tables
    danger     destructive actions (mark lost, delete)

  <Button icon={RefreshCw} loading={isPending} onClick={…}>Run review</Button>

  Size "md" is 44px tall, big enough to tap on a phone. While `loading`,
  the button shows a spinner and can't be pressed twice.
*/
import clsx from 'clsx'
import { LoaderCircle } from 'lucide-react'
import { motion } from 'motion/react'

import { press } from '@/animations/presets'

const LOOKS = {
  primary: 'bg-brand text-on-brand hover:bg-brand-strong shadow-sm',
  secondary: 'bg-surface-raised text-ink border border-line hover:border-line-strong hover:bg-surface',
  ghost: 'text-ink-2 hover:bg-surface-sunken hover:text-ink',
  danger: 'bg-critical-soft text-critical-ink hover:bg-critical hover:text-white',
}

const SIZES = {
  sm: 'h-9 px-3 text-sm gap-1.5',
  md: 'h-11 px-4 text-sm gap-2',
  icon: 'size-11 justify-center',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon: Icon,
  loading = false,
  disabled,
  className,
  children,
  ...props
}) {
  const busy = loading || disabled
  return (
    <motion.button
      type="button"
      {...(busy ? {} : press)}
      disabled={busy}
      aria-busy={loading || undefined}
      className={clsx(
        'inline-flex cursor-pointer items-center rounded-control font-medium whitespace-nowrap',
        'transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-60',
        LOOKS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {loading ? (
        <LoaderCircle aria-hidden className="size-4 animate-spin" />
      ) : (
        Icon && <Icon aria-hidden className="size-4" />
      )}
      {children}
    </motion.button>
  )
}
