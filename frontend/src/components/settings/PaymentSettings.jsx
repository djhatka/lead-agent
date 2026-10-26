/*
  Payments (Task 31): the Settings card.

  The owner's own UPI ID (where customers' money goes, straight to them), the
  name customers see, and polite automatic WhatsApp reminders on/off. Only the
  owner can change it.
*/
import clsx from 'clsx'
import { Save } from 'lucide-react'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { InlineError } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { keys } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'
import { useDueSettings } from '@/hooks/useDues'

const field = 'mt-1 h-11 w-full rounded-control border border-line bg-surface-raised px-3 text-ink outline-none focus:border-brand disabled:opacity-70'

function Form({ s, isOwner }) {
  const b = useBusinessId()
  const queryClient = useQueryClient()
  const [upi, setUpi] = useState(s.upi_id)
  const [payee, setPayee] = useState(s.payee_name)
  const save = useMutation({
    mutationFn: (changes) => api.updateDueSettings(b, changes),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.dueSettings(b), data)
      queryClient.invalidateQueries({ queryKey: keys.dues })
      toast({ title: 'Payment settings saved', tone: 'good' })
    },
    onError: (error) => toast({ title: "Couldn't save", body: error.message, tone: 'critical' }),
  })
  const changed = upi.trim() !== s.upi_id || payee.trim() !== s.payee_name

  return (
    <>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate({ upi_id: upi.trim(), payee_name: payee.trim() })
        }}
      >
        <label className="block text-sm font-medium text-ink">
          Your UPI ID
          <span className="block text-xs font-normal text-ink-3">Find it in GPay / PhonePe / Paytm under your profile. Customers' money goes straight here.</span>
          <input value={upi} onChange={(e) => setUpi(e.target.value)} disabled={!isOwner} maxLength={120}
                 placeholder="yourname@okaxis" autoComplete="off" spellCheck={false} className={field} />
        </label>
        <label className="block text-sm font-medium text-ink">
          Name customers see <span className="font-normal text-ink-3">(optional)</span>
          <input value={payee} onChange={(e) => setPayee(e.target.value)} disabled={!isOwner} maxLength={60}
                 placeholder="Your business name" className={field} />
        </label>
        {isOwner && (
          <Button type="submit" size="sm" icon={Save} disabled={!changed} loading={save.isPending}>
            Save
          </Button>
        )}
      </form>

      <div className="mt-4 flex items-start justify-between gap-4 border-t border-line pt-4">
        <div>
          <p className="text-sm font-medium text-ink">Polite automatic reminders</p>
          <p className="text-xs text-ink-3">
            A WhatsApp on the due date, then after 3 and 7 days (3 at most, 10am–8pm), until it's paid or the customer says
            they've paid.
            {s.reminders_mode === 'practice' && ' Practice mode: recorded, not delivered, until WhatsApp is connected for real.'}
          </p>
        </div>
        <input
          type="checkbox"
          role="switch"
          aria-label="Polite automatic reminders"
          checked={s.auto_reminders}
          disabled={!isOwner || save.isPending || !s.ready}
          onChange={(e) => save.mutate({ auto_reminders: e.target.checked })}
          className={clsx('mt-1 size-5 shrink-0 cursor-pointer accent-[var(--color-brand)] disabled:cursor-not-allowed')}
        />
      </div>
      {!isOwner && <p className="mt-3 text-xs text-ink-3">Only the owner can change this.</p>}
    </>
  )
}

export function PaymentSettings() {
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60_000 })
  const isOwner = ['owner', 'admin'].includes(me.data?.user?.role)
  const query = useDueSettings()

  if (query.isPending) return <Skeleton className="h-64 rounded-card" />
  if (query.isError) return <InlineError error={query.error} onRetry={() => query.refetch()} />
  return (
    <Card>
      <CardHeader title="Payments" subtitle="Customers pay you by UPI from a payment link: advances, fees, dues" />
      <Form key={`${query.data.upi_id}|${query.data.payee_name}`} s={query.data} isOwner={isOwner} />
    </Card>
  )
}
