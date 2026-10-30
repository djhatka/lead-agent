/*
  Payments (Task 31): money customers owe, paid straight to the owner's UPI ID.

  1. The numbers: ₹ recovered this month, ₹ still waiting, ₹ overdue
  2. "Add payment": a walk-in's fee, a member's monthly dues (from an enquiry,
     use "Request payment" inside the enquiry instead)
  3. The list: waiting / paid / cancelled. Customers who pressed "I've paid"
     come first, so the owner just checks their UPI app and confirms.
*/
import clsx from 'clsx'
import { useFeatures } from '@/hooks/useFeatures'
import { AlertTriangle, CheckCircle2, Hourglass, IndianRupee, Plus, Wallet } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { Link } from 'react-router'

import { fadeUp, listItem, stagger } from '@/animations/presets'
import { StatTile } from '@/components/charts/StatTile'
import { PageHeader } from '@/components/layout/PageHeader'
import { DueCard } from '@/components/payments/DueCard'
import { DueForm } from '@/components/payments/DueForm'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, ErrorState, InlineError } from '@/components/ui/States'
import { useDues, useDueSettings, useDueSummary } from '@/hooks/useDues'
import { inr } from '@/styles/tokens'

const TABS = [
  ['open', 'Waiting'],
  ['paid', 'Paid'],
  ['cancelled', 'Cancelled'],
]
const EMPTY = {
  open: ['Nobody owes you anything right now', 'Add a payment, or press "Request payment" inside an enquiry.'],
  paid: ['No payments received yet', 'Payments you mark as paid show up here.'],
  cancelled: ['Nothing cancelled', ''],
}

function Numbers() {
  const summary = useDueSummary()
  if (summary.isPending) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 rounded-card" />)}
      </div>
    )
  }
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
  const s = summary.data
  const change = s.recovered_last_month ? ((s.recovered_this_month - s.recovered_last_month) / s.recovered_last_month) * 100 : null
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
      <StatTile label="Recovered this month" icon={Wallet} value={s.recovered_this_month} format={(n) => inr(Math.round(n))}
                change={change} hint={`${s.paid_this_month} payment${s.paid_this_month === 1 ? '' : 's'} · vs last month`} />
      <StatTile label="Waiting to be paid" icon={Hourglass} value={s.waiting} format={(n) => inr(Math.round(n))}
                hint={`${s.open} payment${s.open === 1 ? '' : 's'}${s.says_paid ? ` · ${s.says_paid} say they've paid` : ''}`} />
      <StatTile label="Overdue" icon={AlertTriangle} value={s.overdue} format={(n) => inr(Math.round(n))}
                hint={s.overdue_count ? `${s.overdue_count} past the due date` : 'Nothing overdue 🎉'} />
    </div>
  )
}

function List({ status }) {
  const dues = useDues(status)
  if (dues.isPending) return <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 rounded-control" />)}</div>
  if (dues.isError) return <InlineError error={dues.error} onRetry={() => dues.refetch()} />
  if (dues.data.length === 0) {
    const [title, body] = EMPTY[status]
    return <EmptyState icon={status === 'paid' ? CheckCircle2 : IndianRupee} title={title} className="py-8">{body}</EmptyState>
  }
  return (
    <motion.ul variants={stagger(0.04)} initial="hidden" animate="show" className="space-y-3">
      {dues.data.map((due) => (
        <motion.li key={due.id} variants={listItem} layout>
          <DueCard due={due} />
        </motion.li>
      ))}
    </motion.ul>
  )
}

export default function Payments() {
  const features = useFeatures()
  const settings = useDueSettings()
  const [tab, setTab] = useState('open')
  const [adding, setAdding] = useState(false)
  const ready = settings.data?.ready

  return (
    <div>
      <PageHeader
        actions={
          ready && !adding && (
            <Button variant="primary" icon={Plus} onClick={() => setAdding(true)}>
              Add payment
            </Button>
          )
        }
      />
      <motion.div variants={stagger(0.07)} initial="hidden" animate="show" className="space-y-6">
        {settings.data && !ready && (
          <motion.div variants={fadeUp}>
            <Card className="border border-warning/40">
              <CardHeader title="Set up payments in 1 minute" subtitle="Add your UPI ID, and customers can pay you with one tap" />
              <p className="text-sm text-ink-2">
                Every payment link opens a small page with a "Pay with any UPI app" button and a QR code. The money goes
                straight to your own UPI account: Lead Intel never touches it.
              </p>
              <Link to="/settings" className="mt-3 inline-flex text-sm font-semibold text-brand hover:underline">
                Add my UPI ID in Settings →
              </Link>
            </Card>
          </motion.div>
        )}

        <motion.div variants={fadeUp}>
          <Numbers />
        </motion.div>

        <AnimatePresence>
          {adding && (
            <motion.div variants={fadeUp} initial="hidden" animate="show" exit="hidden">
              <Card>
                <CardHeader title="Add a payment" subtitle="For a walk-in or a regular customer. From an enquiry, use “Request payment” inside it." />
                <DueForm onDone={() => setAdding(false)} />
              </Card>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.div variants={fadeUp}>
          <Card>
            <div role="tablist" aria-label="Payments" className="mb-4 inline-flex rounded-full border border-line bg-surface-sunken p-1">
              {TABS.map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={tab === key}
                  onClick={() => setTab(key)}
                  className={clsx(
                    'h-9 cursor-pointer rounded-full px-4 text-sm font-medium transition-colors',
                    tab === key ? 'bg-surface-raised text-ink shadow-card' : 'text-ink-3 hover:text-ink',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <List key={tab} status={tab} />
          </Card>
        </motion.div>

        {settings.data?.ready && (
          <p className="text-xs text-ink-3">
            Payments go to <span className="font-medium text-ink-2">{settings.data.upi_id}</span>.
            {!features.on('whatsapp_messaging')
              ? ' Automatic reminders are coming soon. For now, tap Open WhatsApp on a payment to send the reminder yourself.'
              : settings.data.auto_reminders
              ? settings.data.reminders_mode === 'real'
                ? ' Automatic reminders are on (on the due date, then after 3 and 7 days).'
                : ' Automatic reminders are on, in practice mode until WhatsApp is connected for real.'
              : ' Automatic reminders are off.'}{' '}
            <Link to="/settings" className="font-medium text-brand hover:underline">Change</Link>
          </p>
        )}
      </motion.div>
    </div>
  )
}
