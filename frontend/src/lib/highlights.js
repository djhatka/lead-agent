/*
  Plain-English sentences about the period, for the Home page.

  Newer servers send these with /analytics/summary (`highlights`). For
  servers that don't, we write them here from the same numbers.
*/
import { channel, inr, plural } from '@/styles/tokens'

export function deriveHighlights(summary, sources = []) {
  if (summary.highlights?.length) return summary.highlights
  const out = []
  const name = (s) => channel(s.source).label
  const enough = sources.filter((s) => s.leads >= 3)

  if (enough.length >= 2) {
    const busiest = enough.reduce((a, b) => (b.leads > a.leads ? b : a))
    const money = enough.reduce((a, b) => (b.revenue > a.revenue ? b : a))
    if (money.revenue > 0 && busiest.source !== money.source)
      out.push(`${name(busiest)} brought the most enquiries (${busiest.leads}), but ${name(money)} brought the most money: ${inr(money.revenue)} from ${plural(money.leads, 'enquiry', 'enquiries')}.`)
    else if (money.revenue > 0)
      out.push(`${name(money)} is your best channel: ${plural(money.leads, 'enquiry', 'enquiries')} and ${inr(money.revenue)} in sales.`)
  }
  if (summary.leads_change_pct != null && Math.abs(summary.leads_change_pct) >= 1)
    out.push(`Enquiries are ${summary.leads_change_pct > 0 ? 'up' : 'down'} ${Math.abs(Math.round(summary.leads_change_pct))}% on the period before.`)
  if (summary.leads) out.push(`You answered ${summary.replied_within_5_min_pct}% of enquiries within 5 minutes. Fast replies win more sales.`)
  if (summary.unanswered) out.push(`${plural(summary.unanswered, 'enquiry has', 'enquiries have')} had no reply at all.`)
  if (summary.open_hot_leads) out.push(`${plural(summary.open_hot_leads, 'hot enquiry is', 'hot enquiries are')} waiting. Call them first.`)
  return out
}
