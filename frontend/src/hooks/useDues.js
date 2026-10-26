/*
  Payments and dues (Task 31): money customers owe, paid straight to the owner's UPI ID.

    useDueSettings()          UPI ID, name customers see, automatic reminders
    useDueSummary()           ₹ recovered this month, ₹ waiting, ₹ overdue (refreshes every 30 s)
    useDues(status, leadId)   the list (open / paid / cancelled), or one enquiry's payments
    useDue(id)                one due + its ready messages (payment link / reminder)
    useDueAction()            create / send / paid / cancel / reopen, then refresh what it touches
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { keys, LIVE_REFRESH } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'

export function useDueSettings() {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.dueSettings(b), queryFn: () => api.dueSettings(b), enabled: b != null })
}

export function useDueSummary(options = {}) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.dueSummary(b),
    queryFn: () => api.dueSummary(b),
    enabled: b != null,
    refetchInterval: LIVE_REFRESH,
    ...options,
  })
}

export function useDues(status = 'open', leadId) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.dueList(b, status, leadId),
    queryFn: () => api.dues(b, status, leadId),
    enabled: b != null,
    refetchInterval: LIVE_REFRESH,
  })
}

export function useDue(id) {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.due(b, id), queryFn: () => api.due(b, id), enabled: b != null && id != null })
}

/**
 * action = { type: 'create', body } | { type: 'send', id, text, via, kind } | { type: 'paid', id, via }
 *        | { type: 'cancel', id } | { type: 'reopen', id }
 */
export function useDueAction() {
  const b = useBusinessId()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (a) => {
      if (a.type === 'create') return api.createDue(b, a.body)
      if (a.type === 'send') return api.sendDue(b, a.id, a.text, a.via, a.kind)
      if (a.type === 'paid') return api.markDuePaid(b, a.id, a.via)
      if (a.type === 'cancel') return api.cancelDue(b, a.id)
      return api.reopenDue(b, a.id)
    },
    onSuccess: (_result, a) => {
      client.invalidateQueries({ queryKey: keys.dues })
      if (a.type === 'send') {
        // the message is now in the enquiry's chat
        client.invalidateQueries({ queryKey: keys.leads })
        client.invalidateQueries({ queryKey: keys.followups })
      }
    },
  })
}
