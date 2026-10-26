/*
  The Leads page's filters, kept in the address bar
  (/leads?source=instagram&priority=hot&sort=score&page=2).

  So the Overview's "Open hot leads" link, refresh, back button and shared
  links all show exactly the same list. Changing any filter goes back to
  page 1.
*/
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'

const KEYS = ['search', 'source', 'status', 'priority', 'sentiment', 'sort', 'page']
export const PAGE_SIZE = 25

export function useLeadFilters() {
  const [params, setParams] = useSearchParams()

  const filters = useMemo(() => {
    const f = Object.fromEntries(KEYS.map((k) => [k, params.get(k) ?? '']))
    f.sort ||= 'newest'
    f.page = Math.max(1, Number(f.page) || 1)
    return f
  }, [params])

  const setFilter = useCallback(
    (key, value) =>
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          if (value === '' || value == null || (key === 'sort' && value === 'newest')) next.delete(key)
          else next.set(key, String(value))
          if (key !== 'page') next.delete('page')
          return next
        },
        { replace: key === 'search' }, // typing shouldn't add a history entry per letter
      ),
    [setParams],
  )

  const clear = useCallback(() => setParams({}), [setParams])
  const active = KEYS.some((k) => k !== 'page' && k !== 'sort' && filters[k])

  // What the backend expects
  const query = {
    search: filters.search || undefined,
    source: filters.source || undefined,
    status: filters.status || undefined,
    priority: filters.priority || undefined,
    sentiment: filters.sentiment || undefined,
    sort: filters.sort,
    page: filters.page,
    page_size: PAGE_SIZE,
  }

  return { filters, query, setFilter, clear, active, search: params.toString() }
}
