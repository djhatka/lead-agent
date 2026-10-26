/*
  Two small, honest signals in the top bar:

  - "Sample data": this page shows built-in sample data for parts the
    server doesn't have yet. Tap it to see which parts.
  - "Practice AI": the AI is in free mock mode, so its answers come from
    simple rules, not Claude.

  On phones they shrink to icons (the label stays for screen readers).
*/
import { Bot, FlaskConical } from 'lucide-react'

import { isSampleOnlyBusiness } from '@/api/client'
import { Popover } from '@/components/ui/Popover'
import { useAiStatus } from '@/hooks/useAnalytics'
import { useBusinessId } from '@/hooks/useBusiness'
import { useRouteHandle } from '@/hooks/useRouteHandle'
import { useSampleAreas } from '@/hooks/useSampleAreas'

const AREA_NAMES = {
  analytics: 'the numbers',
  leads: 'enquiries',
  content: 'social posts',
  growth: 'weekly reviews',
  reviews: 'Google reviews',
  ai: 'the AI team diary',
  settings: 'business settings',
}

const pill = 'inline-flex h-9 items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold whitespace-nowrap'

function listWords(items) {
  if (items.length < 2) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`
}

export function SamplePill() {
  const used = useSampleAreas()
  const b = useBusinessId()
  const { areas = [] } = useRouteHandle()
  const hits = areas.filter((a) => used.includes(a))
  if (!hits.length) return null
  const everything = isSampleOnlyBusiness(b)

  return (
    <Popover
      label="About the sample data"
      align="right"
      panelClassName="w-80 p-4"
      button={
        <span className={`${pill} bg-warning-soft text-warning-ink`}>
          <FlaskConical aria-hidden className="size-4" />
          <span className="sr-only sm:not-sr-only">Sample data</span>
        </span>
      }
    >
      <p className="text-sm font-semibold text-ink">Some of this page is sample data</p>
      <p className="mt-1.5 text-sm text-ink-2">
        {everything
          ? "This business isn't on the server yet, so everything you see here is built-in sample data."
          : `The server doesn't have ${listWords(hits.map((a) => AREA_NAMES[a] ?? a))} yet, so that part shows built-in sample data.`}
      </p>
      <p className="mt-2 text-xs text-ink-3">
        Changes you make to sample data aren't sent anywhere and reset when you reload the page.
      </p>
    </Popover>
  )
}

export function AiModePill() {
  const status = useAiStatus()
  if (status.data?.mode !== 'mock') return null
  return (
    <Popover
      label="About practice AI"
      align="right"
      panelClassName="w-80 p-4"
      button={
        <span className={`${pill} border border-line bg-surface-sunken text-ink-2`}>
          <Bot aria-hidden className="size-4" />
          <span className="sr-only sm:not-sr-only">Practice AI</span>
        </span>
      }
    >
      <p className="text-sm font-semibold text-ink">The AI is in free practice mode</p>
      <p className="mt-1.5 text-sm text-ink-2">
        Scores, drafts and reviews come from simple built-in rules instead of Claude, so they cost nothing. They still
        show you how everything works.
      </p>
      <p className="mt-2 text-xs text-ink-3">To switch to Claude, set MOCK_AI=false and an API key in the server's .env.</p>
    </Popover>
  )
}
