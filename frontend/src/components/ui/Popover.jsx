/*
  A small panel that opens under a button: menus, explanations.

  <Popover label="Switch business" button={<span>…</span>} align="left">
    {(close) => <button onClick={close}>…</button>}
  </Popover>

  Closes on Escape (focus goes back to the button), on a click outside,
  or when the content calls `close`.
*/
import clsx from 'clsx'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'

import { duration, ease } from '@/animations/presets'

export function Popover({ button, label, children, align = 'left', className, panelClassName, role = 'dialog' }) {
  const [open, setOpen] = useState(false)
  const root = useRef(null)
  const trigger = useRef(null)
  const id = useId()

  useEffect(() => {
    if (!open) return
    const onDown = (e) => !root.current?.contains(e.target) && setOpen(false)
    const onKey = (e) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      trigger.current?.focus()
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={root} className={clsx('relative', className)}>
      <button
        ref={trigger}
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={id}
        aria-haspopup={role === 'menu' ? 'menu' : 'dialog'}
        onClick={() => setOpen((o) => !o)}
        className="flex max-w-full cursor-pointer items-center rounded-control text-left"
      >
        {button}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            id={id}
            role={role}
            aria-label={label}
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1, transition: { duration: duration.base, ease: ease.out } }}
            exit={{ opacity: 0, y: -4, transition: { duration: duration.fast } }}
            className={clsx(
              'absolute top-full z-50 mt-2 w-72 max-w-[calc(100vw-2rem)] origin-top rounded-card border border-line bg-surface-raised p-1.5 shadow-pop',
              align === 'right' ? 'right-0' : 'left-0',
              panelClassName,
            )}
          >
            {typeof children === 'function' ? children(() => setOpen(false)) : children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
