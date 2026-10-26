/*
  One renewal in the list: "Priya · Monthly membership expires in 5 days"
  with a ready message, WhatsApp button, and snooze/stop/renewed actions.
*/
import clsx from 'clsx'
import { Check, Clock, Copy, ExternalLink, Pause, Play, RotateCcw, Send, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'

import { fadeUp } from '@/animations/presets'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { toast } from '@/components/ui/toast'
import { useRenewal, useRenewalAction } from '@/hooks/useRenewals'

const kindColors = {
  expiring_soon: 'bg-warning-soft text-warning-ink border-warning/30',
  expired: 'bg-critical-soft text-critical border-critical/30',
  lapsed: 'bg-surface-sunken text-ink-3 border-line',
}
const kindLabels = {
  expiring_soon: 'Expiring soon',
  expired: 'Expired',
  lapsed: 'Lapsed',
}

export function RenewalCard({ item }) {
  const [expanded, setExpanded] = useState(false)
  const detail = useRenewal(expanded ? item.id : null)
  const action = useRenewalAction()

  const copy = (text) => {
    navigator.clipboard.writeText(text)
    toast({ title: 'Message copied', tone: 'good' })
  }

  const doAction = (type) => {
    action.mutate({ type, id: item.id, days: 1 }, {
      onSuccess: () => {
        const msgs = { send: 'Marked as sent', snooze: 'Snoozed for 1 day', stop: 'Stopped', renewed: 'Marked as renewed', resume: 'Resumed' }
        toast({ title: msgs[type] || 'Done', tone: 'good' })
        if (type === 'stop' || type === 'renewed') setExpanded(false)
      },
    })
  }

  const draft = detail.data?.draft

  return (
    <Card className="transition-shadow hover:shadow-lg">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full cursor-pointer items-start gap-3 text-left"
      >
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2">
            <span className="truncate font-semibold text-ink">{item.customer}</span>
            <span className={clsx('shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium', kindColors[item.kind])}>
              {kindLabels[item.kind]}
            </span>
          </p>
          <p className="mt-0.5 text-sm text-ink-2">{item.reason}</p>
          {item.reminders_sent > 0 && (
            <p className="mt-0.5 text-xs text-ink-3">{item.reminders_sent} reminder{item.reminders_sent !== 1 ? 's' : ''} sent</p>
          )}
        </div>
        <span className="shrink-0 text-sm font-semibold text-brand">{expanded ? 'Close' : 'Open'}</span>
      </button>

      <AnimatePresence>
        {expanded && draft && (
          <motion.div variants={fadeUp} initial="hidden" animate="show" exit="hidden" className="mt-4 space-y-3 border-t border-line pt-4">
            <div className="rounded-control bg-surface-sunken p-3">
              <p className="mb-1 text-xs font-medium text-ink-3">Ready message</p>
              <p className="whitespace-pre-line text-sm text-ink">{draft.text}</p>
            </div>
            <p className="text-xs text-ink-3">{draft.note}</p>

            <div className="flex flex-wrap gap-2">
              {draft.how === 'whatsapp' && draft.link ? (
                <Button
                  as="a"
                  href={`${draft.link}?text=${encodeURIComponent(draft.text)}`}
                  target="_blank"
                  rel="noopener"
                  variant="primary"
                  icon={ExternalLink}
                  size="sm"
                  onClick={() => doAction('send')}
                >
                  Open WhatsApp
                </Button>
              ) : (
                <Button variant="primary" icon={Copy} size="sm" onClick={() => { copy(draft.text); doAction('send') }}>
                  Copy &amp; mark sent
                </Button>
              )}
              <Button variant="outline" icon={Check} size="sm" onClick={() => doAction('renewed')} disabled={action.isPending}>
                Renewed
              </Button>
              <Button variant="ghost" icon={Clock} size="sm" onClick={() => doAction('snooze')} disabled={action.isPending}>
                Snooze
              </Button>
              <Button variant="ghost" icon={X} size="sm" onClick={() => doAction('stop')} disabled={action.isPending}>
                Stop
              </Button>
            </div>
          </motion.div>
        )}
        {expanded && detail.isPending && (
          <motion.div variants={fadeUp} initial="hidden" animate="show" exit="hidden" className="mt-4 pt-4 border-t border-line">
            <p className="text-sm text-ink-3">Loading message…</p>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  )
}
