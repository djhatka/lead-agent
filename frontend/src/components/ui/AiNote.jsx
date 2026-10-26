/*
  How the AI's work is shown, everywhere:

  <WhyNote>Offer posts brought 9 enquiries…</WhyNote>
      every AI decision says why, so the owner can trust or question it

  <AiDraft label="Draft by AI">…</AiDraft>
      anything the AI wrote that isn't approved yet: dashed border, a label,
      and nothing happens until the owner presses a button
*/
import clsx from 'clsx'
import { Sparkles } from 'lucide-react'

export function WhyNote({ children, label = 'Why', className }) {
  if (!children) return null
  return (
    <p className={clsx('flex gap-1.5 text-sm text-ink-2', className)}>
      <Sparkles aria-hidden className="mt-0.5 size-3.5 shrink-0 text-brand" />
      <span>
        <span className="font-semibold text-ink">{label}: </span>
        {children}
      </span>
    </p>
  )
}

export function AiLabel({ children = 'Draft by AI', className }) {
  return (
    <span className={clsx('flex w-fit items-center gap-1 text-xs font-semibold text-brand', className)}>
      <Sparkles aria-hidden className="size-3.5" />
      {children}
    </span>
  )
}

export function AiDraft({ label = 'Draft by AI', action, className, children }) {
  return (
    <div className={clsx('ai-draft rounded-control p-3', className)}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <AiLabel>{label}</AiLabel>
        {action}
      </div>
      {children}
    </div>
  )
}
