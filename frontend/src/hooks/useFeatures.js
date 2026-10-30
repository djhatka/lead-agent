/*
  What the server really offers (GET /features). While loading, or if it can't be reached, everything counts as on,
  so nothing flickers away. In "light" mode the server hides what needs a platform approval.

    const { on } = useFeatures();  on('connect_apps')
*/
import { useQuery } from '@tanstack/react-query'

import { ALL_FEATURES, api } from '@/api/client'

export function useFeatures() {
  const query = useQuery({ queryKey: ['features'], queryFn: api.features, staleTime: 5 * 60 * 1000 })
  const data = query.data ?? ALL_FEATURES
  return { ...data, on: (name) => data[name] !== false }
}
