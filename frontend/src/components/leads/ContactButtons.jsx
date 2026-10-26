/*
  Call or WhatsApp a customer with one tap. These only open the phone's
  dialer or WhatsApp with the number filled in: the owner still decides
  what to say and presses send.
*/
import clsx from 'clsx'
import { MessageCircle, Phone } from 'lucide-react'

import { leadTitle } from '@/styles/tokens'

const button =
  'flex size-11 shrink-0 items-center justify-center rounded-control border border-line bg-surface-raised text-ink-2 transition-colors hover:border-line-strong hover:text-brand'

export function ContactButtons({ lead, className }) {
  if (!lead.phone) return null
  const who = leadTitle(lead)
  return (
    <div className={clsx('flex gap-1.5', className)}>
      <a href={`tel:+91${lead.phone}`} aria-label={`Call ${who}`} title="Call" className={button} onClick={(e) => e.stopPropagation()}>
        <Phone aria-hidden className="size-[18px]" />
      </a>
      <a
        href={`https://wa.me/91${lead.phone}`}
        target="_blank"
        rel="noreferrer"
        aria-label={`WhatsApp ${who}`}
        title="Open in WhatsApp"
        className={button}
        onClick={(e) => e.stopPropagation()}
      >
        <MessageCircle aria-hidden className="size-[18px]" />
      </a>
    </div>
  )
}
