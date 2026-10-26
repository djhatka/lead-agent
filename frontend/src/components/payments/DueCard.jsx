/*
  One payment a customer owes (Task 31): who, how much, for what, and where it stands
  ("Overdue by 3 days", "Due today", "Paid on 24 Oct").

  Actions, all one tap:
    Send link / Remind   opens the ready message (see SendBox) to send on WhatsApp
    Confirm paid         when the customer pressed "I've paid" on their payment page
    Mark paid            UPI / Cash / Card / Other
    Cancel, Undo, Reopen
*/
import clsx from 'clsx'
import { BellRing, Check, Link2, Send, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { SendBox } from '@/components/payments/SendBox'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmButton } from '@/components/ui/ConfirmButton'
import { Skeleton } from '@/components/ui/Skeleton'
import { toast } from '@/components/ui/toast'
import { useDue, useDueAction } from '@/hooks/useDues'
import { inr } from '@/styles/tokens'

const PAID_BY = [
  ['upi', 'UPI'],
  ['cash', 'Cash'],
  ['card', 'Card'],
  ['other', 'Other'],
]
const PAID_NAMES = { upi: 'UPI', cash: 'cash', card: 'card', bank: 'bank transfer', other: 'other' }

function stateTone(due) {
  if (due.status === 'paid') return 'good'
  if (due.status === 'cancelled') return 'neutral'
  if (due.overdue_days > 0) return 'critical'
  if (due.label === 'Due today') return 'warning'
  return 'brand'
}

function Sender({ due, kind, onClose }) {
  const detail = useDue(due.id)
  const action = useDueAction()
  if (detail.isPending) return <Skeleton className="h-32 w-full rounded-control" />
  if (detail.isError) return <p className="text-sm text-critical-ink">{detail.error.message}</p>
  const ready = detail.data.ready
  return (
    <SendBox
      key={kind}
      label={kind === 'request' ? 'Payment link message' : 'Reminder'}
      text={ready[kind]}
      how={ready.how}
      link={ready.link}
      note={ready.note}
      busy={action.isPending}
      onCancel={onClose}
      onSend={(via, text) =>
        action.mutate(
          { type: 'send', id: due.id, text, via, kind },
          {
            onSuccess: (result) => {
              if (result.delivery === 'failed') {
                toast({ title: 'Not sent', body: result.delivery_error, tone: 'critical', seconds: 10 })
                return
              }
              toast({ title: kind === 'request' ? 'Payment link sent ✅' : 'Reminder sent ✅', tone: 'good' })
              onClose()
            },
            onError: (error) => toast({ title: "Couldn't send", body: error.message, tone: 'critical' }),
          },
        )
      }
    />
  )
}

export function DueCard({ due, compact = false }) {
  const action = useDueAction()
  const [sending, setSending] = useState(null) // 'request' | 'reminder' | null
  const [choosing, setChoosing] = useState(false) // picking how it was paid
  const open = due.status === 'open'
  const run = (a, done) =>
    action.mutate(a, {
      onSuccess: () => done && toast({ title: done, tone: 'good' }),
      onError: (error) => toast({ title: "Couldn't do that", body: error.message, tone: 'critical' }),
    })
  const paid = (via) => {
    setChoosing(false)
    run({ type: 'paid', id: due.id, via }, `${inr(due.amount)} marked as paid 💰`)
  }

  const name = due.lead_id && !compact ? (
    <Link to={`/leads/${due.lead_id}`} className="font-semibold text-ink hover:text-brand hover:underline">
      {due.customer_name}
    </Link>
  ) : (
    <span className="font-semibold text-ink">{due.customer_name}</span>
  )

  return (
    <div className={clsx('rounded-control border p-4', due.customer_says_paid_at && open ? 'border-accent/50 bg-accent-soft/40' : 'border-line bg-surface-raised')}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2">
            {name}
            <Badge tone={stateTone(due)}>{due.label}</Badge>
            {open && due.customer_says_paid_at && <Badge tone="accent">Says they've paid</Badge>}
          </p>
          <p className="mt-0.5 text-sm text-ink-2">{due.purpose}</p>
          <p className="mt-0.5 text-xs text-ink-3">
            {[
              due.status === 'paid' && due.paid_via && `Paid by ${PAID_NAMES[due.paid_via] ?? due.paid_via}`,
              due.reminders_sent > 0 && `${due.reminders_sent} reminder${due.reminders_sent === 1 ? '' : 's'} sent`,
              open && due.due_date && !due.auto_remind && 'No automatic reminders',
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
        <p className="num text-xl font-bold text-ink">{inr(due.amount)}</p>
      </div>

      {sending ? (
        <div className="mt-3">
          <Sender due={due} kind={sending} onClose={() => setSending(null)} />
        </div>
      ) : choosing ? (
        <div className="mt-3 flex flex-wrap items-center gap-2" role="group" aria-label="How was it paid?">
          <span className="text-sm font-medium text-ink">Paid by</span>
          {PAID_BY.map(([via, label]) => (
            <Button key={via} size="sm" variant={via === 'upi' ? 'primary' : 'secondary'} onClick={() => paid(via)}>
              {label}
            </Button>
          ))}
          <Button size="sm" variant="ghost" onClick={() => setChoosing(false)}>
            Cancel
          </Button>
        </div>
      ) : open ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {due.customer_says_paid_at ? (
            <Button size="sm" variant="primary" icon={Check} loading={action.isPending} onClick={() => paid('upi')}>
              Confirm paid
            </Button>
          ) : (
            <Button size="sm" variant="secondary" icon={Check} onClick={() => setChoosing(true)}>
              Mark paid
            </Button>
          )}
          <Button size="sm" variant="secondary" icon={Send} onClick={() => setSending('request')}>
            Send link
          </Button>
          <Button size="sm" variant="ghost" icon={BellRing} onClick={() => setSending('reminder')}>
            Remind
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={Link2}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(due.pay_url)
                toast({ title: 'Payment page link copied', tone: 'good' })
              } catch {
                window.open(due.pay_url, '_blank', 'noreferrer')
              }
            }}
          >
            Copy link
          </Button>
          <span className="ml-auto">
            <ConfirmButton size="sm" variant="ghost" icon={X} question="Cancel this payment?" confirmLabel="Yes, cancel"
                           onConfirm={() => run({ type: 'cancel', id: due.id }, 'Payment cancelled')}>
              Cancel
            </ConfirmButton>
          </span>
        </div>
      ) : (
        <div className="mt-2">
          <Button size="sm" variant="ghost" loading={action.isPending}
                  onClick={() => run({ type: 'reopen', id: due.id }, 'Moved back to waiting')}>
            {due.status === 'paid' ? 'Undo paid' : 'Reopen'}
          </Button>
        </div>
      )}
    </div>
  )
}
