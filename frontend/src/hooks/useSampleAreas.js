/*
  Which parts of the current business's page came from built-in sample
  data (because the server doesn't have them yet). The top bar shows a
  "Sample data" pill when the page uses any of them.
*/
import { useSyncExternalStore } from 'react'

import { sampleUsage } from '@/api/client'
import { useBusinessId } from '@/hooks/useBusiness'

export function useSampleAreas() {
  const used = useSyncExternalStore(sampleUsage.subscribe, sampleUsage.snapshot)
  const b = useBusinessId()
  return [...(used[String(b)] ?? []), ...(used.any ?? [])]
}
