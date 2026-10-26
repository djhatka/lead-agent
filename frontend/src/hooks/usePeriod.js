/*
  The time window the numbers cover: last 7, 30 or 90 days.

  It lives in the address bar (?days=30), so a refresh, the back button
  or a shared link keeps the same view, and every page reads the same value.

  const { days, setDays } = usePeriod()
*/
import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

export const PERIODS = [7, 30, 90]
const DEFAULT_DAYS = 30

export function usePeriod() {
  const [params, setParams] = useSearchParams()
  const asked = Number(params.get('days'))
  const days = PERIODS.includes(asked) ? asked : DEFAULT_DAYS

  const setDays = useCallback(
    (next) =>
      setParams(
        (current) => {
          const updated = new URLSearchParams(current)
          if (next === DEFAULT_DAYS) updated.delete('days')
          else updated.set('days', String(next))
          return updated
        },
        { replace: true }, // switching period shouldn't fill the back button history
      ),
    [setParams],
  )

  return { days, setDays }
}
