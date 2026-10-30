/*
  Plan & billing: which plan the owner is on, what each plan includes, and how to pay.

  While online payments are off (the launch version) the owner pays you by UPI or bank transfer
  and you switch the plan on from the admin box at the bottom. When Razorpay is added later the
  server reports payments_mode "real" and this page says so (checkout is the next thing to build).
  This page never uses sample data: money screens must show what the server really says.
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Check, Copy, ShieldCheck } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'

import { fadeUp, stagger } from '@/animations/presets'
import { api } from '@/api/client'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { useBusinessId } from '@/hooks/useBusiness'
import { inr, shortDate } from '@/styles/tokens'

const field = 'h-11 w-full rounded-control border border-line bg-surface px-3 text-sm text-ink focus:outline-2 focus:outline-brand'

function useBilling() {
  const b = useBusinessId()
  const status = useQuery({ queryKey: ['billing', 'status', b], queryFn: () => api.billingStatus(b), enabled: b != null })
  const plans = useQuery({ queryKey: ['billing', 'plans'], queryFn: api.billingPlans, staleTime: 10 * 60_000 })
  const payments = useQuery({ queryKey: ['billing', 'payments', b], queryFn: () => api.billingPayments(b), enabled: b != null })
  return { b, status, plans, payments }
}

const STATE_TONE = { active: 'good', trial: 'neutral', trialing: 'neutral', grace: 'warning', cancelled: 'warning', expired: 'critical' }

function Current({ status }) {
  const s = status.data
  return (
    <Card>
      <CardHeader title="Your plan" subtitle={s.message} />
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-2xl font-semibold text-ink">{s.plan_name}</span>
        <Badge tone={STATE_TONE[s.state] ?? 'neutral'}>{s.state === 'trial' || s.state === 'trialing' ? 'Free trial' : s.state}</Badge>
        {s.days_left != null && <span className="text-sm text-ink-2">{s.days_left} days left</span>}
        {s.ends_at && <span className="text-sm text-ink-3">until {shortDate(s.ends_at)}</span>}
      </div>
    </Card>
  )
}

function HowToPay({ status }) {
  const s = status.data
  const [copied, setCopied] = useState(false)
  if (s.payments_mode !== 'manual') {
    return (
      <Card>
        <CardHeader title="How to pay" />
        <p className="text-sm text-ink-2">
          {s.payments_mode === 'real'
            ? 'Online payment is on. Choose a plan above to pay by UPI, card or net banking.'
            : 'Payments are in practice mode here, so nothing real is charged.'}
        </p>
      </Card>
    )
  }
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(s.pay_upi_id)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast({ title: "Couldn't copy", body: 'Select the UPI id and copy it by hand.', tone: 'critical' })
    }
  }
  return (
    <Card>
      <CardHeader title="How to pay" subtitle="Online payment is coming soon. For now, pay by UPI or bank transfer." />
      <ol className="list-decimal space-y-2 pl-5 text-sm text-ink-2">
        <li>Pick a plan above and pay its monthly price.</li>
        {s.pay_upi_id ? (
          <li className="flex flex-wrap items-center gap-2">
            Pay to this UPI id:
            <span className="font-semibold text-ink">{s.pay_upi_id}</span>
            <Button size="sm" variant="secondary" icon={copied ? Check : Copy} onClick={copy}>{copied ? 'Copied' : 'Copy'}</Button>
          </li>
        ) : (
          <li>Ask {s.pay_contact || 'us'} for the UPI or bank details.</li>
        )}
        {s.pay_note && <li>{s.pay_note}</li>}
        <li>Send {s.pay_contact ? `the screenshot to ${s.pay_contact}` : 'us the screenshot'}. We switch your plan on the same day.</li>
      </ol>
    </Card>
  )
}

function Plans({ plans, status }) {
  const current = status.data.plan
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {plans.data.map((p) => (
        <Card key={p.code} className={clsx(p.code === current && 'ring-2 ring-brand')}>
          <div className="flex items-baseline justify-between">
            <h3 className="text-lg font-semibold text-ink">{p.name}</h3>
            {p.code === current && <Badge tone="good">Your plan</Badge>}
          </div>
          <p className="text-sm text-ink-3">{p.tagline}</p>
          <p className="mt-3 text-2xl font-semibold text-ink">{inr(p.price)}<span className="text-sm font-normal text-ink-3"> / month</span></p>
          <ul className="mt-3 space-y-1.5 text-sm text-ink-2">
            {p.highlights.map((h) => (
              <li key={h} className="flex gap-2"><Check aria-hidden className="mt-0.5 size-4 shrink-0 text-brand" />{h}</li>
            ))}
            <li className="flex gap-2"><Check aria-hidden className="mt-0.5 size-4 shrink-0 text-brand" />{Math.round(p.storage_mb / 1024)} GB for photos and videos</li>
          </ul>
        </Card>
      ))}
    </div>
  )
}

function History({ payments }) {
  const list = payments.data ?? []
  return (
    <Card>
      <CardHeader title="Payments" subtitle="What you have paid so far" />
      {list.length === 0 ? (
        <p className="text-sm text-ink-3">No payments yet.</p>
      ) : (
        <ul className="divide-y divide-line text-sm">
          {list.map((p, i) => (
            <li key={p.id ?? i} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <span className="text-ink">{inr(p.amount)} <span className="text-ink-3">· {p.plan}</span></span>
              <span className="text-ink-3">{p.paid_at ? shortDate(p.paid_at) : ''} · {p.status}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

/** Only for you (the admin): switch a plan on after the owner has paid by hand. */
function AdminActivate({ plans, currentBusiness }) {
  const client = useQueryClient()
  const [form, setForm] = useState({ business_id: currentBusiness ?? '', plan: 'growth', days: 30 })
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const activate = useMutation({
    mutationFn: () => api.billingActivate({ business_id: Number(form.business_id), plan: form.plan, days: Number(form.days) }),
    onSuccess: (a) => {
      toast({ title: 'Plan switched on', body: `${a.plan_name}: ${a.message}`, tone: 'good' })
      client.invalidateQueries({ queryKey: ['billing'] })
    },
    onError: (err) => toast({ title: "Couldn't activate", body: err.message, tone: 'critical' }),
  })
  return (
    <Card>
      <CardHeader title="Switch on a plan (admin)" subtitle="Use after an owner has paid you by UPI or bank transfer. Doing it again adds days." />
      <form
        onSubmit={(e) => { e.preventDefault(); activate.mutate() }}
        className="flex flex-wrap items-end gap-3"
      >
        <label className="text-sm font-medium text-ink">
          Business id
          <input type="number" min="1" required value={form.business_id} onChange={set('business_id')} className={clsx(field, 'mt-1.5 w-28')} />
        </label>
        <label className="text-sm font-medium text-ink">
          Plan
          <select value={form.plan} onChange={set('plan')} className={clsx(field, 'mt-1.5 cursor-pointer')}>
            {plans.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium text-ink">
          Days
          <input type="number" min="1" max="366" required value={form.days} onChange={set('days')} className={clsx(field, 'mt-1.5 w-24')} />
        </label>
        <Button type="submit" icon={ShieldCheck} loading={activate.isPending}>Switch on</Button>
      </form>
    </Card>
  )
}

export default function Billing() {
  const { b, status, plans, payments } = useBilling()
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60_000 })

  const failed = status.error || plans.error
  return (
    <div>
      <PageHeader />
      {failed ? (
        <ErrorState title="Couldn't load your plan" error={status.error ?? plans.error} onRetry={() => { status.refetch(); plans.refetch() }} />
      ) : !status.data || !plans.data ? (
        <div className="space-y-4"><Skeleton className="h-28" /><Skeleton className="h-40" /></div>
      ) : (
        <motion.div variants={stagger(0.07)} initial="hidden" animate="show" className="space-y-6">
          <motion.div variants={fadeUp}><Current status={status} /></motion.div>
          <motion.div variants={fadeUp}><Plans plans={plans} status={status} /></motion.div>
          <motion.div variants={fadeUp}><HowToPay status={status} /></motion.div>
          <motion.div variants={fadeUp}><History payments={payments} /></motion.div>
          {me.data?.role === 'admin' && (
            <motion.div variants={fadeUp}><AdminActivate plans={plans.data} currentBusiness={b} /></motion.div>
          )}
        </motion.div>
      )}
    </div>
  )
}
