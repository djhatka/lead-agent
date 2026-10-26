/*
  Renewals (Task 32): memberships and services about to expire.

  "Priya's monthly membership ends in 5 days" → a ready WhatsApp message the owner
  can send in one tap. Like follow-ups, but for things that expire (gym memberships,
  service packages, subscriptions), not enquiries that went quiet.
*/
import clsx from 'clsx'
import { CheckCircle2, Plus, RefreshCw } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'

import { fadeUp, listItem, stagger } from '@/animations/presets'
import { PageHeader } from '@/components/layout/PageHeader'
import { RenewalCard } from '@/components/renewals/RenewalCard'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, ErrorState } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { useRenewalAction, useRenewals } from '@/hooks/useRenewals'

function AddForm({ onDone }) {
  const action = useRenewalAction()
  const [form, setForm] = useState({ customer_name: '', phone: '', service: '', expiry_date: '', renewal_amount: '' })
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const valid = form.customer_name.trim() && form.service.trim() && form.expiry_date

  const submit = (e) => {
    e.preventDefault()
    const body = {
      customer_name: form.customer_name.trim(),
      phone: form.phone.trim() || undefined,
      service: form.service.trim(),
      expiry_date: form.expiry_date,
      renewal_amount: form.renewal_amount ? Number(form.renewal_amount) : undefined,
    }
    action.mutate({ type: 'create', body }, {
      onSuccess: () => { toast({ title: 'Renewal added', tone: 'good' }); onDone() },
      onError: (err) => toast({ title: "Couldn't add", body: err.message, tone: 'critical' }),
    })
  }

  const inputCls = 'h-10 w-full rounded-control border border-line bg-surface-raised px-3 text-sm text-ink placeholder:text-ink-3 focus:border-brand focus:outline-none'
  return (
    <form onSubmit={submit} className="space-y-3">
      <input className={inputCls} placeholder="Customer name" value={form.customer_name} onChange={set('customer_name')} required />
      <input className={inputCls} placeholder="Phone (optional)" value={form.phone} onChange={set('phone')} />
      <input className={inputCls} placeholder="Service (e.g. Monthly membership)" value={form.service} onChange={set('service')} required />
      <div className="grid grid-cols-2 gap-3">
        <input className={inputCls} type="date" placeholder="Expiry date" value={form.expiry_date} onChange={set('expiry_date')} required />
        <input className={inputCls} type="number" min="0" placeholder="Amount (optional)" value={form.renewal_amount} onChange={set('renewal_amount')} />
      </div>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={!valid || action.isPending}>Add renewal</Button>
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  )
}

export default function Renewals() {
  const query = useRenewals()
  const [adding, setAdding] = useState(false)

  return (
    <div>
      <PageHeader
        actions={
          !adding && (
            <Button variant="primary" icon={Plus} onClick={() => setAdding(true)}>
              Add renewal
            </Button>
          )
        }
      />
      <motion.div variants={stagger(0.07)} initial="hidden" animate="show" className="space-y-6">
        <AnimatePresence>
          {adding && (
            <motion.div variants={fadeUp} initial="hidden" animate="show" exit="hidden">
              <Card>
                <CardHeader title="Add a renewal" subtitle="Track when a customer's membership or service expires" />
                <AddForm onDone={() => setAdding(false)} />
              </Card>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.div variants={fadeUp}>
          {query.isPending && (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 rounded-card" />)}
            </div>
          )}
          {query.isError && !query.data && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
          {query.data && query.data.count === 0 && (
            <EmptyState icon={RefreshCw} title="No renewals coming up" className="py-8">
              When you add a membership or service with an expiry date, it will show up here before it expires.
            </EmptyState>
          )}
          {query.data && query.data.count > 0 && (
            <motion.ul variants={stagger(0.04)} initial="hidden" animate="show" className="space-y-3">
              {query.data.items.map((item) => (
                <motion.li key={item.id} variants={listItem} layout>
                  <RenewalCard item={item} />
                </motion.li>
              ))}
            </motion.ul>
          )}
        </motion.div>

        {query.data && (
          <p className="text-xs text-ink-3">
            Reminding {query.data.settings.remind_days_before} days before expiry.
            Renewals expired more than 30 days ago are hidden.{' '}
            <a href="/settings" className="font-medium text-brand hover:underline">Change</a>
          </p>
        )}
      </motion.div>
    </div>
  )
}
