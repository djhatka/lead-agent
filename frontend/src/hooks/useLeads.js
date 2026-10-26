/*
  Enquiry data for the pages.

    useLeads(filters)       a page of enquiries (keeps the old page on screen while the next loads)
    useLead(id)             one enquiry with its full chat
    useUpdateLead()         change status / value / details
    useAddMessage()         add a chat message
    useAnalyzeLead()        ask the AI team to score an enquiry again

  Lists refresh every 30 s by themselves (and instantly when the live
  feed reports a change). After any change, every list and the numbers
  are refreshed, so the dashboard never shows stale totals.
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { keepWithinBusiness, keys, LIVE_REFRESH } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'

export function useLeads(filters = {}, options = {}) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.leadList(b, filters),
    queryFn: () => api.leads(b, filters),
    enabled: b != null,
    placeholderData: keepWithinBusiness(b), // no flash of an empty table between pages
    refetchInterval: LIVE_REFRESH,
    ...options,
  })
}

export function useLead(id) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.lead(b, id),
    queryFn: () => api.lead(b, id),
    enabled: b != null && id != null && id !== '',
  })
}

function useRefreshAfterChange() {
  const client = useQueryClient()
  const b = useBusinessId()
  return (lead) => {
    if (lead?.id) client.setQueryData(keys.lead(b, lead.id), lead) // show the new version straight away
    client.invalidateQueries({ queryKey: keys.leads })
    client.invalidateQueries({ queryKey: keys.analytics })
    client.invalidateQueries({ queryKey: keys.followups }) // a status change can end a follow-up reminder
  }
}

export function useUpdateLead() {
  const refresh = useRefreshAfterChange()
  const b = useBusinessId()
  return useMutation({
    mutationFn: ({ id, changes }) => api.updateLead(b, id, changes),
    onSuccess: refresh,
  })
}

export function useAddMessage() {
  const client = useQueryClient()
  const b = useBusinessId()
  return useMutation({
    mutationFn: ({ id, direction, text }) => api.addMessage(b, id, { direction, text }),
    onSuccess: (_message, { id }) => {
      client.invalidateQueries({ queryKey: keys.lead(b, id) })
      client.invalidateQueries({ queryKey: keys.leads })
      client.invalidateQueries({ queryKey: keys.analytics })
      client.invalidateQueries({ queryKey: keys.followups }) // a reply resets the follow-up clock
    },
  })
}

export function useAnalyzeLead() {
  const refresh = useRefreshAfterChange()
  const client = useQueryClient()
  const b = useBusinessId()
  return useMutation({
    mutationFn: (id) => api.analyzeLead(b, id),
    onSuccess: (lead) => {
      refresh(lead)
      client.invalidateQueries({ queryKey: keys.agentRuns })
    },
  })
}
