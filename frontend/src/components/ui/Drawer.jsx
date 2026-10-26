/*
  A panel that slides in from the right (full screen on phones), over a
  dimmed page. Used for editing a post and replaying an AI run.

  <Drawer eyebrow="Post" title="Diwali offer" onClose={close} footer={<Button…/>}>
    …scrolling content…
  </Drawer>

  Render it inside <AnimatePresence> so it can slide out. Closes with Esc,
  the ✕ button, or a click on the dimmed background; the page behind
  doesn't scroll while it's open.
*/
import { X } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect } from 'react'

import { drawer, fadeIn } from '@/animations/presets'
import { useLockScroll } from '@/hooks/useLockScroll'

export function Drawer({ eyebrow, title, onClose, footer, children, wide = false }) {
  useLockScroll()

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <>
      <motion.div
        variants={fadeIn}
        initial="hidden"
        animate="show"
        exit="exit"
        onClick={onClose}
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]"
      />
      <motion.aside
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : eyebrow}
        variants={drawer}
        initial="hidden"
        animate="show"
        exit="exit"
        className={`fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-surface shadow-pop ${wide ? 'max-w-2xl' : 'max-w-lg'}`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 pt-5 pb-4">
          <div className="min-w-0">
            {eyebrow && <div className="text-xs text-ink-3">{eyebrow}</div>}
            <h2 className="text-xl font-semibold">{title}</h2>
          </div>
          <button
            type="button"
            autoFocus
            onClick={onClose}
            aria-label="Close"
            className="flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-control text-ink-2 hover:bg-surface-sunken"
          >
            <X aria-hidden className="size-5" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto">{children}</div>
        {footer && (
          <footer className="border-t border-line bg-surface px-5 py-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">{footer}</footer>
        )}
      </motion.aside>
    </>
  )
}
