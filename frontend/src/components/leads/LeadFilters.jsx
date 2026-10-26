/*
  One row of filters above the lead table (they scope everything below).

  Search waits until you stop typing for 0.3 s before asking the backend,
  so typing "creta" makes one request, not five. Dropdowns are the
  browser's own (<select>): keyboard-friendly and the right size on phones.
*/
import clsx from 'clsx'
import { Flame, Search, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { CHANNELS, SENTIMENTS, STATUSES } from '@/styles/tokens'

const shape = 'h-11 rounded-control border px-3 text-sm outline-none transition-colors focus-visible:border-brand'
const control = `${shape} border-line bg-surface-raised text-ink hover:border-line-strong`

function Select({ label, value, onChange, children }) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} className={clsx(control, 'shrink-0 cursor-pointer pr-8')}>
      {children}
    </select>
  )
}

export function LeadFilters({ filters, setFilter, clear, active, total }) {
  const [text, setText] = useState(filters.search)
  const [shown, setShown] = useState(filters.search)
  const timer = useRef(null)

  // The address bar changed by itself (back button, a link): show its search text.
  if (filters.search !== shown) {
    setShown(filters.search)
    setText(filters.search)
  }

  function onType(value) {
    setText(value)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      setShown(value.trim())
      setFilter('search', value.trim())
    }, 300)
  }

  useEffect(() => () => clearTimeout(timer.current), [])

  const hotOnly = filters.priority === 'hot'

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="relative min-w-0 flex-1 basis-48 sm:max-w-xs">
        <span className="sr-only">Search enquiries</span>
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
        <input
          type="search"
          value={text}
          onChange={(e) => onType(e.target.value)}
          placeholder="Name, phone, service, message…"
          className={clsx(control, 'w-full pl-9')}
        />
      </label>

      <button
        type="button"
        aria-pressed={hotOnly}
        onClick={() => setFilter('priority', hotOnly ? '' : 'hot')}
        className={clsx(
          'inline-flex shrink-0 cursor-pointer items-center gap-1.5 font-medium sm:order-last',
          hotOnly ? `${shape} border-accent bg-accent-soft text-accent-ink` : control,
        )}
      >
        <Flame aria-hidden className="size-4" /> Hot only
      </button>

      {/* Phones: one row that scrolls sideways instead of five wrapped rows */}
      <div className="-mx-4 flex w-[calc(100%+2rem)] gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:w-auto sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0">
      <Select label="Channel" value={filters.source} onChange={(v) => setFilter('source', v)}>
        <option value="">All channels</option>
        {CHANNELS.map((c) => (
          <option key={c.key} value={c.key}>
            {c.label}
          </option>
        ))}
      </Select>

      <Select label="Status" value={filters.status} onChange={(v) => setFilter('status', v)}>
        <option value="">Any status</option>
        {Object.entries(STATUSES).map(([key, s]) => (
          <option key={key} value={key}>
            {s.label}
          </option>
        ))}
      </Select>

      <Select label="Tone" value={filters.sentiment} onChange={(v) => setFilter('sentiment', v)}>
        <option value="">Any tone</option>
        {Object.entries(SENTIMENTS).map(([key, s]) => (
          <option key={key} value={key}>
            {s.label}
          </option>
        ))}
      </Select>

      <Select label="Sort by" value={filters.sort} onChange={(v) => setFilter('sort', v)}>
        <option value="newest">Newest first</option>
        <option value="score">Highest score</option>
        <option value="value">Biggest sale</option>
        <option value="oldest">Oldest first</option>
      </Select>
      </div>

      {active && (
        <button
          type="button"
          onClick={() => {
            clearTimeout(timer.current)
            setText('')
            setShown('')
            clear()
          }}
          className="inline-flex h-11 cursor-pointer items-center gap-1 rounded-control px-3 text-sm font-medium text-ink-2 hover:bg-surface-sunken"
        >
          <X aria-hidden className="size-4" /> Clear
        </button>
      )}

      <p className="ml-auto text-sm text-ink-3 sm:order-last" aria-live="polite">
        {total != null && `${total.toLocaleString('en-IN')} ${total === 1 ? 'enquiry' : 'enquiries'}`}
      </p>
    </div>
  )
}
