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
import { useLanguage } from '@/hooks/useLanguage'
import { useRouteHandle } from '@/hooks/useRouteHandle'
import { useSampleAreas } from '@/hooks/useSampleAreas'

const AREA_NAMES = {
  en: {
    analytics: 'the numbers',
    leads: 'enquiries',
    content: 'social posts',
    growth: 'weekly reviews',
    reviews: 'Google reviews',
    ai: 'the AI team diary',
    settings: 'business settings',
  },
  hi: {
    analytics: 'आँकड़े',
    leads: 'पूछताछ',
    content: 'सोशल पोस्ट',
    growth: 'साप्ताहिक समीक्षाएँ',
    reviews: 'Google रिव्यू',
    ai: 'AI टीम की डायरी',
    settings: 'बिज़नेस सेटिंग्स',
  },
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
  const { t, lang } = useLanguage()
  if (!hits.length) return null
  const everything = isSampleOnlyBusiness(b)
  const names = AREA_NAMES[lang] ?? AREA_NAMES.en

  return (
    <Popover
      label={t('status.aboutSampleData')}
      align="right"
      panelClassName="w-80 p-4"
      button={
        <span className={`${pill} bg-warning-soft text-warning-ink`}>
          <FlaskConical aria-hidden className="size-4" />
          <span className="sr-only sm:not-sr-only">{t('status.sampleData')}</span>
        </span>
      }
    >
      <p className="text-sm font-semibold text-ink">{t('status.someSampleData')}</p>
      <p className="mt-1.5 text-sm text-ink-2">
        {everything
          ? t('status.sampleDataEverything')
          : t('status.sampleDataPartial', { areas: listWords(hits.map((a) => names[a] ?? a)) })}
      </p>
      <p className="mt-2 text-xs text-ink-3">{t('status.sampleDataFooter')}</p>
    </Popover>
  )
}

export function AiModePill() {
  const status = useAiStatus()
  const { t } = useLanguage()
  if (status.data?.mode !== 'mock') return null
  return (
    <Popover
      label={t('status.aboutPracticeAi')}
      align="right"
      panelClassName="w-80 p-4"
      button={
        <span className={`${pill} border border-line bg-surface-sunken text-ink-2`}>
          <Bot aria-hidden className="size-4" />
          <span className="sr-only sm:not-sr-only">{t('status.practiceAi')}</span>
        </span>
      }
    >
      <p className="text-sm font-semibold text-ink">{t('status.practiceAiHeading')}</p>
      <p className="mt-1.5 text-sm text-ink-2">{t('status.practiceAiBody')}</p>
      <p className="mt-2 text-xs text-ink-3">{t('status.practiceAiFooter')}</p>
    </Popover>
  )
}
