/*
  "Request a payment" (Task 31): amount, what it's for, and an optional due date.

  From an enquiry (leadId given) the customer's name and number come from it;
  on the Payments page you type them (a walk-in, a member paying monthly).
  Once saved, the ready message with the payment link appears, to send on
  WhatsApp straight away.
*/
import clsx from 'clsx'
import { IndianRupee } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { SendBox } from '@/components/payments/SendBox'
import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/toast'
import { useDueAction, useDueSettings } from '@/hooks/useDues'

const field = 'mt-1 h-11 w-full rounded-control border border-line bg-surface-raised px-3 text-ink outline-none focus:border-brand'

export function DueForm({ leadId, onDone }) {
  const settings = useDueSettings()
  const action = useDueAction()
  const [form, setForm] = useState({ customer_name: '', phone: '', amount: '', purpose: '', due_date: '', auto_remind: true })
  const [made, setMade] = useState(null) // { due, ready } once saved
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  if (settings.data && !settings.data.ready) {
    return (
      <p className="rounded-control bg-warning-soft px-3 py-2 text-sm text-warning-ink">
        Add your UPI ID first, so customers know where to pay.{' '}
        <Link to="/settings" className="font-medium underline">Settings → Payments</Link>
      </p>
    )
  }

  if (made) {
    return (
      <div className="space-y-2">
        <p className="text-sm font-medium text-good-ink">Saved. Now send them the payment link:</p>
        <SendBox
          label="Payment link message"
          text={made.ready.request}
          how={made.ready.how}
          link={made.ready.link}
          note={made.ready.note}
          busy={action.isPending}
          onCancel={onDone}
          onSend={(via, text) =>
            action.mutate(
              { type: 'send', id: made.due.id, text, via, kind: 'request' },
              {
                onSuccess: (result) => {
                  if (result.delivery === 'failed') {
                    toast({ title: 'Not sent', body: result.delivery_error, tone: 'critical', seconds: 10 })
                    return
                  }
                  toast({ title: 'Payment link sent ✅', tone: 'good' })
                  onDone?.()
                },
                onError: (error) => toast({ title: "Couldn't send", body: error.message, tone: 'critical' }),
              },
            )
          }
        />
      </div>
    )
  }

  function save(event) {
    event.preventDefault()
    const body = {
      amount: Number(form.amount),
      purpose: form.purpose.trim(),
      due_date: form.due_date || null,
      auto_remind: form.auto_remind,
      ...(leadId ? { lead_id: Number(leadId) } : { customer_name: form.customer_name.trim(), phone: form.phone.trim() }),
    }
    action.mutate(
      { type: 'create', body },
      { onSuccess: setMade, onError: (error) => toast({ title: "Couldn't save", body: error.message, tone: 'critical' }) },
    )
  }

  return (
    <form onSubmit={save} className="space-y-3">
      {!leadId && (
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm font-medium text-ink">
            Customer's name
            <input required maxLength={100} value={form.customer_name} onChange={set('customer_name')} className={field} placeholder="Priya Sharma" />
          </label>
          <label className="text-sm font-medium text-ink">
            WhatsApp number <span className="font-normal text-ink-3">(optional)</span>
            <input type="tel" maxLength={20} value={form.phone} onChange={set('phone')} className={field} placeholder="98100 12345" />
          </label>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
        <label className="text-sm font-medium text-ink">
          Amount (₹)
          <input required type="number" min="1" max="1000000" step="1" inputMode="numeric" value={form.amount}
                 onChange={set('amount')} className={clsx(field, 'num')} placeholder="2000" />
        </label>
        <label className="text-sm font-medium text-ink">
          For
          <input required minLength={2} maxLength={200} value={form.purpose} onChange={set('purpose')} className={field}
                 placeholder="Advance for ceramic coating" />
        </label>
      </div>
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <label className="text-sm font-medium text-ink">
          Due date <span className="font-normal text-ink-3">(optional)</span>
          <input type="date" value={form.due_date} onChange={set('due_date')} className={clsx(field, 'w-48')} />
        </label>
        {form.due_date && (
          <label className="flex h-11 items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={form.auto_remind} onChange={set('auto_remind')} className="size-4 accent-[var(--color-brand)]" />
            Polite automatic reminders
          </label>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" icon={IndianRupee} loading={action.isPending}>
          Create payment link
        </Button>
        {onDone && (
          <Button variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  )
}
