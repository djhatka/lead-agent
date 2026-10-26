/*
  Payments inside an enquiry (Task 31): "Request payment" for an advance or a
  booking, and this customer's payments with where each one stands.
*/
import { IndianRupee } from 'lucide-react'
import { useState } from 'react'

import { DueCard } from '@/components/payments/DueCard'
import { DueForm } from '@/components/payments/DueForm'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { useDues } from '@/hooks/useDues'

export function LeadPayments({ leadId }) {
  const dues = useDues('all', leadId)
  const [adding, setAdding] = useState(false)
  if (dues.isError) return null // an older server without payments: the drawer works as before

  return (
    <section className="border-t border-line px-5 py-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold tracking-wide text-ink-3 uppercase">Payments</h3>
        {!adding && (
          <Button size="sm" variant="ghost" icon={IndianRupee} onClick={() => setAdding(true)}>
            Request payment
          </Button>
        )}
      </div>
      {adding && (
        <div className="mb-4 rounded-control border border-line bg-surface-raised p-4">
          <DueForm leadId={leadId} onDone={() => setAdding(false)} />
        </div>
      )}
      {dues.isPending ? (
        <Skeleton className="h-20 w-full rounded-control" />
      ) : dues.data.length === 0 ? (
        !adding && <p className="text-sm text-ink-3">No payments yet. Ask for an advance or a booking amount with a UPI link.</p>
      ) : (
        <ul className="space-y-3">
          {dues.data.map((due) => (
            <li key={due.id}>
              <DueCard due={due} compact />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
