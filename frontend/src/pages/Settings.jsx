/*
  Settings: the business details the AI writes from, and the social accounts.

  - Business profile: services, brand voice, who the customers are, and the
    Google review link (sent in review requests). Only changed fields are
    saved; leaving with unsaved changes is flagged on the Save button.
  - Social accounts: what's connected, what needs reconnecting (an expired
    login stops scheduled posts), and adding a new one.
*/
import clsx from 'clsx'
import { ExternalLink, Plug, Plus, Save, Unplug, X } from 'lucide-react'
import { motion } from 'motion/react'
import { useState, useCallback } from 'react'

import { fadeUp, stagger } from '@/animations/presets'
import { PageHeader } from '@/components/layout/PageHeader'
import { AutoReply } from '@/components/settings/AutoReply'
import { FollowUpSettings } from '@/components/settings/FollowUpSettings'
import { PaymentSettings } from '@/components/settings/PaymentSettings'
import { RenewalSettings } from '@/components/settings/RenewalSettings'
import { PhoneAlerts } from '@/components/settings/PhoneAlerts'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { ConfirmButton } from '@/components/ui/ConfirmButton'
import { QueryCard } from '@/components/ui/QueryCard'
import { LanguageToggle } from '@/components/ui/LanguageToggle'
import { Skeleton } from '@/components/ui/Skeleton'
import { InlineError } from '@/components/ui/States'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { toast } from '@/components/ui/toast'
import { useFeatures } from '@/hooks/useFeatures'
import { useLanguage } from '@/hooks/useLanguage'
import { useAddSocialAccount, useBusinessProfile, useSocialAccounts, useUpdateBusiness, useUpdateSocialAccount } from '@/hooks/useSettings'
import { count, platform, PLATFORMS, shortDate } from '@/styles/tokens'

const field = 'w-full rounded-control border border-line bg-surface-raised px-3 py-2 text-sm text-ink outline-none transition-colors focus-visible:border-brand'

const EDITABLE = ['name', 'city', 'area', 'phone', 'opening_hours', 'services', 'brand_voice', 'target_audience', 'google_review_link']

const toForm = (b) => ({
  ...Object.fromEntries(EDITABLE.map((k) => [k, b[k] ?? ''])),
  services: (b.services ?? []).map((s) => (typeof s === 'string' ? s : s.name)),
})

function Field({ label, hint, htmlFor, children, className }) {
  return (
    <div className={className}>
      <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-ink-3">{hint}</p>}
    </div>
  )
}

function ServicesInput({ value, onChange }) {
  const [text, setText] = useState('')
  const add = () => {
    const name = text.trim()
    if (name && !value.includes(name)) onChange([...value, name])
    setText('')
  }
  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {value.map((s) => (
          <span key={s} className="inline-flex items-center gap-1 rounded-full bg-surface-sunken py-1 pr-1 pl-3 text-sm text-ink">
            {s}
            <button
              type="button"
              onClick={() => onChange(value.filter((x) => x !== s))}
              aria-label={`Remove ${s}`}
              className="flex size-6 cursor-pointer items-center justify-center rounded-full text-ink-3 hover:bg-line hover:text-ink"
            >
              <X aria-hidden className="size-3.5" />
            </button>
          </span>
        ))}
      </div>
      <div className="mt-2 flex gap-2">
        <input
          id="services"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          placeholder="Add a service, e.g. Personal training"
          className={field}
        />
        <Button icon={Plus} onClick={add} disabled={!text.trim()}>
          Add
        </Button>
      </div>
    </div>
  )
}

function ProfileForm({ business }) {
  const update = useUpdateBusiness()
  const [form, setForm] = useState(() => toForm(business))
  const saved = toForm(business)
  const changes = Object.fromEntries(EDITABLE.filter((k) => JSON.stringify(form[k]) !== JSON.stringify(saved[k])).map((k) => [k, form[k]]))
  const dirty = Object.keys(changes).length > 0
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e?.target ? e.target.value : e }))

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        update.mutate(changes, { onSuccess: () => toast({ title: 'Saved', body: 'The AI will use these details from now on.', tone: 'good' }) })
      }}
      className="space-y-5"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Business name" htmlFor="name">
          <input id="name" required value={form.name} onChange={set('name')} className={field} />
        </Field>
        <Field label="Type of business" htmlFor="category">
          <input id="category" value={business.category_label ?? business.category ?? ''} disabled className={clsx(field, 'opacity-70')} />
        </Field>
        <Field label="Area" htmlFor="area">
          <input id="area" value={form.area} onChange={set('area')} className={field} />
        </Field>
        <Field label="City" htmlFor="city">
          <input id="city" value={form.city} onChange={set('city')} className={field} />
        </Field>
        <Field label="Business WhatsApp number" htmlFor="phone">
          <input id="phone" inputMode="tel" value={form.phone} onChange={set('phone')} className={field} />
        </Field>
        <Field label="Opening hours" htmlFor="hours">
          <input id="hours" value={form.opening_hours} onChange={set('opening_hours')} placeholder="10 am – 8 pm, closed Tuesday" className={field} />
        </Field>
      </div>

      <Field label="Services you sell" hint="The AI uses these to understand enquiries and plan posts." htmlFor="services">
        <ServicesInput value={form.services} onChange={set('services')} />
      </Field>

      <Field label="Brand voice" hint="How your posts and replies should sound." htmlFor="voice">
        <textarea id="voice" rows={3} value={form.brand_voice} onChange={set('brand_voice')} placeholder="Warm and friendly, a little Hinglish, never pushy." className={clsx(field, 'resize-y')} />
      </Field>

      <Field label="Who your customers are" hint="The AI writes posts for these people." htmlFor="audience">
        <textarea id="audience" rows={3} value={form.target_audience} onChange={set('target_audience')} placeholder="Working professionals aged 25–40 who live nearby." className={clsx(field, 'resize-y')} />
      </Field>

      <Field label="Google review link" hint="Sent in the 'please review us' WhatsApp message after every sale." htmlFor="review-link">
        <div className="flex gap-2">
          <input id="review-link" type="url" value={form.google_review_link} onChange={set('google_review_link')} placeholder="https://g.page/r/…/review" className={field} />
          {form.google_review_link && (
            <a
              href={form.google_review_link}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-control border border-line bg-surface-raised px-3 text-sm font-medium text-ink-2 hover:border-line-strong"
            >
              <ExternalLink aria-hidden className="size-4" /> Test
            </a>
          )}
        </div>
      </Field>

      {update.isError && <p role="alert" className="text-sm text-critical-ink">{update.error.message}</p>}

      <div className="flex flex-wrap items-center justify-end gap-3 border-t border-line pt-4">
        {dirty && <span className="text-sm text-warning-ink">You have unsaved changes</span>}
        {dirty && (
          <Button variant="ghost" onClick={() => setForm(saved)}>
            Undo changes
          </Button>
        )}
        <Button type="submit" variant="primary" icon={Save} disabled={!dirty} loading={update.isPending}>
          Save
        </Button>
      </div>
    </form>
  )
}

function Profile() {
  const profile = useBusinessProfile()
  return (
    <Card>
      <CardHeader title="Business profile" subtitle="The AI reads this before it writes a post, a reply or a review." />
      {profile.isPending ? (
        <div className="space-y-4">
          <Skeleton className="h-11 w-full" />
          <Skeleton className="h-11 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : profile.isError ? (
        <InlineError error={profile.error} onRetry={() => profile.refetch()} />
      ) : (
        <ProfileForm key={profile.data.id} business={profile.data} />
      )}
    </Card>
  )
}

const ACCOUNT_STATUS = {
  connected: { label: 'Connected', tone: 'good' },
  expired: { label: 'Login expired', tone: 'critical' },
  disconnected: { label: 'Not connected', tone: 'neutral' },
}

function AddAccount({ existing }) {
  const add = useAddSocialAccount()
  // 'google' and 'whatsapp' connect via the dedicated Connections page; 'linkedin' is OAuth-only.
  const options = Object.keys(PLATFORMS).filter((p) => !['google', 'whatsapp', 'linkedin'].includes(p) && !existing.includes(p))
  const [chosen, setChosen] = useState('')
  const [handle, setHandle] = useState('')
  const platformKey = chosen || options[0]
  if (!options.length) return null
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        add.mutate(
          { platform: platformKey, handle },
          { onSuccess: () => {
            toast({ title: `${platform(platformKey).label} added`, tone: 'good' })
            setHandle('')
            setChosen('')
          } },
        )
      }}
      className="mt-4 flex flex-wrap items-end gap-2 border-t border-line pt-4"
    >
      <div>
        <label htmlFor="new-platform" className="mb-1.5 block text-sm font-medium text-ink">
          Add an account
        </label>
        <select id="new-platform" value={platformKey} onChange={(e) => setChosen(e.target.value)} className={clsx(field, 'h-11 cursor-pointer')}>
          {options.map((p) => (
            <option key={p} value={p}>
              {platform(p).label}
            </option>
          ))}
        </select>
      </div>
      <div className="min-w-40 flex-1">
        <label htmlFor="new-handle" className="sr-only">
          Handle or page name
        </label>
        <input id="new-handle" value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="@yourbusiness" className={clsx(field, 'h-11')} />
      </div>
      <Button type="submit" icon={Plus} loading={add.isPending}>
        Add
      </Button>
      {add.isError && <p role="alert" className="w-full text-sm text-critical-ink">{add.error.message}</p>}
    </form>
  )
}

// Platforms that connect via full OAuth redirect (not a simple toggle).
// Clicking Connect POSTs to /connections/<platform>/start and follows the URL.
const OAUTH_PLATFORMS = new Set(['instagram', 'facebook', 'google', 'linkedin'])

function useOAuthConnect() {
  const [loading, setLoading] = useState(null)  // platform key while in-flight
  const start = useCallback(async (platformKey) => {
    setLoading(platformKey)
    try {
      const res = await fetch(`/connections/${platformKey}/start`, { method: 'POST' })
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const { url } = await res.json()
      window.location.href = url
    } catch (err) {
      toast({ title: `Couldn't start ${platformKey} connect`, body: err.message, tone: 'critical' })
      setLoading(null)
    }
  }, [])
  return { start, loading }
}

function Accounts() {
  const accounts = useSocialAccounts()
  const update = useUpdateSocialAccount()
  const oauth = useOAuthConnect()
  const features = useFeatures()

  const setStatus = (a, status, message) =>
    update.mutate({ id: a.id, changes: { status } }, { onSuccess: () => toast({ title: message, tone: status === 'connected' ? 'good' : 'neutral' }) })

  return (
    <QueryCard query={accounts} title="Social accounts" subtitle="Where your posts go out and enquiries come in" skeleton="h-64">
      {(list) => (
        <>
          <ul className="divide-y divide-line">
            {list.map((a) => {
              const p = platform(a.platform)
              const s = ACCOUNT_STATUS[a.status] ?? { label: a.status, tone: 'neutral' }
              const busy = update.isPending && update.variables?.id === a.id
              const oauthBusy = oauth.loading === a.platform
              const isOAuth = OAUTH_PLATFORMS.has(a.platform)
              return (
                <li key={a.id} className="flex flex-wrap items-center gap-3 py-3">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-control bg-surface-sunken">
                    <p.icon aria-hidden className="size-5 text-ink-2" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-ink">{p.label}</p>
                    <p className="truncate text-xs text-ink-3">
                      {[a.handle || 'No account linked', a.followers != null && `${count(a.followers)} followers`, a.status === 'connected' && a.connected_at && `since ${shortDate(a.connected_at)}`]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>
                  </div>
                  <Badge tone={s.tone}>{s.label}</Badge>
                  {a.status === 'connected' ? (
                    <ConfirmButton size="sm" icon={Unplug} question="Disconnect?" confirmLabel="Disconnect" variant="ghost" loading={busy} onConfirm={() => setStatus(a, 'disconnected', `${p.label} disconnected`)}>
                      Disconnect
                    </ConfirmButton>
                  ) : isOAuth && !features.on('connect_apps') ? (
                    <span className="text-xs text-ink-3">Coming soon</span>
                  ) : isOAuth ? (
                    <Button size="sm" variant={a.status === 'expired' ? 'primary' : 'secondary'} icon={Plug} loading={oauthBusy} onClick={() => oauth.start(a.platform)}>
                      {a.status === 'expired' ? 'Reconnect' : 'Connect'}
                    </Button>
                  ) : (
                    <Button size="sm" variant={a.status === 'expired' ? 'primary' : 'secondary'} icon={Plug} loading={busy} onClick={() => setStatus(a, 'connected', `${p.label} connected`)}>
                      {a.status === 'expired' ? 'Reconnect' : 'Connect'}
                    </Button>
                  )}
                  {a.status === 'expired' && (
                    <p className="w-full text-xs text-critical-ink">Scheduled posts to {p.label} can't go out until you reconnect.</p>
                  )}
                </li>
              )
            })}
          </ul>
          {update.isError && <p role="alert" className="mt-2 text-sm text-critical-ink">{update.error.message}</p>}
          <AddAccount existing={list.map((a) => a.platform)} />
        </>
      )}
    </QueryCard>
  )
}

export default function Settings() {
  const { t } = useLanguage()
  const features = useFeatures()
  return (
    <div>
      <PageHeader />
      <motion.div variants={stagger(0.07)} initial="hidden" animate="show" className="grid gap-6 xl:grid-cols-[3fr_2fr]">
        <motion.div variants={fadeUp}>
          <Profile />
        </motion.div>
        <div className="space-y-6">
          {features.on('whatsapp_messaging') && (
            <motion.div variants={fadeUp}>
              <AutoReply />
            </motion.div>
          )}
          <motion.div variants={fadeUp}>
            <FollowUpSettings />
          </motion.div>
          <motion.div variants={fadeUp}>
            <PaymentSettings />
          </motion.div>
          <motion.div variants={fadeUp}>
            <RenewalSettings />
          </motion.div>
          {features.on('whatsapp_messaging') && (
            <motion.div variants={fadeUp}>
              <PhoneAlerts />
            </motion.div>
          )}
          <motion.div variants={fadeUp}>
            <Accounts />
          </motion.div>
          <motion.div variants={fadeUp}>
            <Card>
              <CardHeader title={t('settings.language.title')} subtitle={t('settings.language.subtitle')} />
              <LanguageToggle />
            </Card>
          </motion.div>
          <motion.div variants={fadeUp}>
            <Card>
              <CardHeader title="Appearance" subtitle="Light, dark, or follow your phone" />
              <ThemeToggle />
            </Card>
          </motion.div>
        </div>
      </motion.div>
    </div>
  )
}
