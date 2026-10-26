/*
  The list of leads.

  Big screens: a table (lead · channel · score · mood · status · received · value).
  Phones: one compact card per lead (tables don't fit a 375px screen).

  Clicking a row (or Tab + Enter on the lead's name) opens its detail
  drawer; the filters stay in the address so closing returns to the same list.
  Rows slide in one after another, without bounce (it's a data table).
*/
import clsx from 'clsx'
import { motion } from 'motion/react'
import { Link, useNavigate } from 'react-router'

import { listItem, stagger } from '@/animations/presets'
import { ScoreRing } from '@/components/leads/ScoreRing'
import { ChannelBadge, PriorityBadge, SentimentBadge, StatusBadge } from '@/components/ui/Badge'
import { inr, leadTitle, serviceLabel, timeAgo } from '@/styles/tokens'

function Interest({ lead }) {
  const parts = [lead.car_model, serviceLabel(lead.service)].filter(Boolean)
  return parts.length ? <span className="text-ink-2">{parts.join(' · ')}</span> : null
}

export function LeadTable({ leads, search, pageKey }) {
  const navigate = useNavigate()
  const open = (id) => navigate({ pathname: `/leads/${id}`, search })

  return (
    <>
      {/* Desktop table */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs font-medium text-ink-3">
              <th className="py-3 pr-3 pl-5 font-medium">Enquiry</th>
              <th className="px-3 py-3 font-medium">Channel</th>
              <th className="px-3 py-3 font-medium">Score</th>
              <th className="px-3 py-3 font-medium">Tone</th>
              <th className="px-3 py-3 font-medium">Status</th>
              <th className="px-3 py-3 font-medium">Received</th>
              <th className="py-3 pr-5 pl-3 text-right font-medium">Value</th>
            </tr>
          </thead>
          <motion.tbody key={pageKey} variants={stagger(0.025)} initial="hidden" animate="show" className="divide-y divide-line">
            {leads.map((lead) => (
              <motion.tr
                key={lead.id}
                variants={listItem}
                onClick={() => open(lead.id)}
                className={clsx(
                  'cursor-pointer transition-colors hover:bg-surface-sunken/70',
                  lead.analysis?.priority === 'hot' && 'bg-accent-soft/40',
                )}
              >
                {/* w-full + max-w-0: this column takes the spare width and its text shortens with "…" */}
                <td className="w-full max-w-0 py-3 pr-3 pl-5">
                  <div className="flex items-center gap-2">
                    <Link
                      to={{ pathname: `/leads/${lead.id}`, search }}
                      onClick={(e) => e.stopPropagation()}
                      className="truncate font-semibold text-ink hover:text-brand"
                    >
                      {leadTitle(lead)}
                    </Link>
                    {lead.analysis?.priority === 'hot' && <PriorityBadge priority="hot" />}
                  </div>
                  <p className="mt-0.5 truncate text-ink-3">
                    <Interest lead={lead} />
                    {(lead.car_model || lead.service) && ' — '}
                    {lead.first_message}
                  </p>
                </td>
                <td className="px-3 py-3 whitespace-nowrap">
                  <ChannelBadge source={lead.source} />
                </td>
                <td className="px-3 py-3 whitespace-nowrap">
                  <ScoreRing score={lead.analysis?.score} size={36} />
                </td>
                <td className="px-3 py-3 whitespace-nowrap">
                  {lead.analysis ? <SentimentBadge sentiment={lead.analysis.sentiment} /> : <span className="text-ink-3">—</span>}
                </td>
                <td className="px-3 py-3 whitespace-nowrap">
                  <StatusBadge status={lead.status} />
                </td>
                <td className="px-3 py-3 whitespace-nowrap text-ink-3">{timeAgo(lead.created_at)}</td>
                <td className="num py-3 pr-5 pl-3 text-right whitespace-nowrap text-ink">
                  {lead.job_value ? inr(lead.job_value) : <span className="text-ink-3">—</span>}
                </td>
              </motion.tr>
            ))}
          </motion.tbody>
        </table>
      </div>

      {/* Phone cards */}
      <motion.ul key={`m-${pageKey}`} variants={stagger(0.03)} initial="hidden" animate="show" className="divide-y divide-line md:hidden">
        {leads.map((lead) => (
          <motion.li key={lead.id} variants={listItem}>
            <Link
              to={{ pathname: `/leads/${lead.id}`, search }}
              className={clsx('flex gap-3 px-4 py-3', lead.analysis?.priority === 'hot' && 'bg-accent-soft/40')}
            >
              <ScoreRing score={lead.analysis?.score} size={40} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate font-semibold text-ink">{leadTitle(lead)}</p>
                  <span className="shrink-0 text-xs text-ink-3">{timeAgo(lead.created_at)}</span>
                </div>
                <p className="truncate text-sm text-ink-3">{lead.first_message}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <ChannelBadge source={lead.source} className="text-xs" />
                  {lead.analysis?.priority === 'hot' && <PriorityBadge priority="hot" />}
                  {lead.analysis && <SentimentBadge sentiment={lead.analysis.sentiment} />}
                  <StatusBadge status={lead.status} />
                </div>
              </div>
            </Link>
          </motion.li>
        ))}
      </motion.ul>
    </>
  )
}
