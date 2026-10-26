/*
  Which business the dashboard is showing.

  There's no login yet, so the owner (or Anmol, testing) picks a business
  in the top bar. The choice is remembered in this browser. Every data
  hook reads the current business itself, so pages never pass it around.

    const { business, businesses, setBusiness } = useBusiness()
    const b = useBusinessId()        // null until the list has loaded
*/
import { useQuery } from '@tanstack/react-query'
import { useCallback, useSyncExternalStore } from 'react'

import { api } from '@/api/client'
import { keys } from '@/hooks/queryKeys'

const STORAGE_KEY = 'growth-partner-business'
const listeners = new Set()

function readChoice() {
  try {
    return Number(localStorage.getItem(STORAGE_KEY)) || null
  } catch {
    return null
  }
}

let choice = readChoice()

function subscribe(notify) {
  listeners.add(notify)
  return () => listeners.delete(notify)
}

export function useBusinesses() {
  return useQuery({ queryKey: keys.businesses, queryFn: api.businesses, staleTime: 5 * 60_000 })
}

export function useBusiness() {
  const list = useBusinesses()
  const chosen = useSyncExternalStore(subscribe, () => choice)
  const businesses = list.data ?? []
  const business = businesses.find((b) => b.id === chosen) ?? businesses[0] ?? null

  const setBusiness = useCallback((id) => {
    choice = Number(id)
    try {
      localStorage.setItem(STORAGE_KEY, String(choice))
    } catch {
      // Not remembered, but still switched for this visit.
    }
    listeners.forEach((notify) => notify())
  }, [])

  return { business, businesses, setBusiness, query: list }
}

export function useBusinessId() {
  return useBusiness().business?.id ?? null
}
