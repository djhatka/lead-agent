/*
  The business's numbers and the server's health.

    useSummary(days)    headline numbers vs the period before, plus plain-English highlights
    useSources(days)    per channel: enquiries, sales, ₹
    useFunnel(days)     received → replied → won
    useTiming(days)     busiest hours and days, and win rate by reply speed
    useServices(days)   what customers ask for
    useTrend(days)      enquiries and sales per day
    useHealth()         is the backend up?
    useAiStatus()       is the AI real (Claude) or the free practice mode?

  Switching period keeps the old numbers on screen while the new ones
  load, so they count to the new value instead of blanking.
*/
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { keepWithinBusiness, keys, LIVE_REFRESH } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'

function useNumbers(name, key, days, options = {}) {
  const b = useBusinessId()
  return useQuery({
    queryKey: key(b, days),
    queryFn: () => api[name](b, days),
    enabled: b != null,
    placeholderData: keepWithinBusiness(b),
    ...options,
  })
}

export const useSummary = (days) => useNumbers('summary', keys.summary, days, { refetchInterval: LIVE_REFRESH })
export const useSources = (days) => useNumbers('sources', keys.sources, days)
export const useFunnel = (days) => useNumbers('funnel', keys.funnel, days)
export const useTiming = (days) => useNumbers('timing', keys.timing, days)
export const useServices = (days) => useNumbers('services', keys.services, days)
export const useTrend = (days) => useNumbers('trend', keys.trend, days)

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: api.health,
    refetchInterval: 60_000, // notice within a minute if the backend goes down
    retry: false,
  })
}

export function useAiStatus() {
  return useQuery({ queryKey: keys.aiStatus, queryFn: api.aiStatus, refetchInterval: 5 * 60_000, retry: false })
}
