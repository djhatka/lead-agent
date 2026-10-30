/*
  Connected apps: where an owner links their Instagram, Facebook, WhatsApp
  and Google Business Profile.

  Why this also proves the business is really theirs: "Connect" opens the
  platform's OWN login page (Meta's or Google's). Only someone who can log
  in to the business's account there can finish it, and we never see their
  password, only a key the platform gives us (stored locked/encrypted).

  How it works:
    Instagram / Facebook / Google  → the browser goes to the platform's page,
                                     the owner approves, the platform sends them
                                     back here (?connected=… or ?error=…)
    WhatsApp                        → Meta's popup (Embedded Signup) on this page

  On a laptop without real platform keys, every button runs in practice
  mode: it comes straight back "connected", so the whole flow can be tried.
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Info, Plug, ShieldCheck, Unplug, X } from 'lucide-react'
import { useSearchParams } from 'react-router'

import { api } from '@/api/client'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ConfirmButton } from '@/components/ui/ConfirmButton'
import { Skeleton } from '@/components/ui/Skeleton'
import { InlineError } from '@/components/ui/States'
import { useFeatures } from '@/hooks/useFeatures'
import { toast } from '@/components/ui/toast'
import { useBusiness } from '@/hooks/useBusiness'
import { whatsappSignup } from '@/lib/whatsappSignup'
import { platform as platformLook, when } from '@/styles/tokens'

const APPS = [
  {
    key: 'whatsapp',
    look: 'whatsapp',
    name: 'WhatsApp Business',
    does: 'Enquiries arrive by themselves, you reply from the dashboard, and happy customers get a "please review us" message.',
  },
  {
    key: 'instagram',
    look: 'instagram',
    name: 'Instagram',
    does: 'DMs arrive as enquiries, replies go out, and your planned posts publish on time with real reach numbers.',
  },
  {
    key: 'facebook',
    look: 'facebook',
    name: 'Facebook Page',
    does: 'Messenger enquiries and replies, posts on your Page, and their numbers.',
  },
  {
    key: 'google',
    look: 'google',
    name: 'Google Business Profile',
    does: 'Your Google reviews arrive every 30 minutes, the AI drafts replies, and you post them with one click.',
  },
]

const STATUS = {
  connected: { label: 'Connected', tone: 'good' },
  expired: { label: 'Needs reconnecting', tone: 'warning' },
  error: { label: 'Problem', tone: 'critical' },
}

function Banner({ tone, icon: Icon, children, onClose }) {
  const look = tone === 'good' ? 'bg-good-soft text-good-ink' : tone === 'critical' ? 'bg-critical-soft text-critical-ink' : 'bg-brand-soft text-brand'
  return (
    <div role={tone === 'critical' ? 'alert' : 'status'} className={`flex items-start gap-3 rounded-card p-4 ${look}`}>
      <Icon aria-hidden className="mt-0.5 size-5 shrink-0" />
      <div className="flex-1 text-sm">{children}</div>
      {onClose && (
        <button type="button" onClick={onClose} aria-label="Close" className="cursor-pointer opacity-70 hover:opacity-100">
          <X className="size-4" />
        </button>
      )}
    </div>
  )
}

function AppCard({ app, connection, mode, isOwner, businessId, setup }) {
  const queryClient = useQueryClient()
  const look = platformLook(app.look)
  const Icon = look.icon
  const status = connection ? (STATUS[connection.status] ?? { label: connection.status, tone: 'neutral' }) : null
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['connections'] })

  const connect = useMutation({
    mutationFn: async () => {
      if (app.key !== 'whatsapp') {
        // Off to Instagram's / Facebook's / Google's own login page. They send the owner back here.
        window.location.assign(await api.startConnection(businessId, app.key))
        return 'redirecting'
      }
      const answer = mode === 'real' ? await whatsappSignup(setup.whatsapp_signup) : { code: 'mock' }
      return api.connectWhatsapp(businessId, answer)
    },
    onSuccess: (result) => {
      if (result === 'redirecting') return
      toast({ title: `${app.name} connected`, tone: 'good' })
      refresh()
    },
    onError: (error) => toast({ title: `Couldn't connect ${app.name}`, body: error.message, tone: 'critical' }),
  })

  const disconnect = useMutation({
    mutationFn: () => api.disconnect(connection.id),
    onSuccess: () => {
      toast({ title: `${app.name} disconnected` })
      refresh()
    },
    onError: (error) => toast({ title: "Couldn't disconnect", body: error.message, tone: 'critical' }),
  })

  const connected = connection?.status === 'connected'

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-control" style={{ background: `color-mix(in srgb, ${look.color} 15%, transparent)`, color: look.color }}>
          <Icon aria-hidden className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-ink">{app.name}</h2>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {status ? <Badge tone={status.tone}>{status.label}</Badge> : <Badge>Not connected</Badge>}
            {mode === 'mock' && <Badge tone="warning">Practice mode</Badge>}
          </div>
        </div>
      </div>

      <p className="text-sm text-ink-2">{app.does}</p>

      {connection && (
        <p className="text-sm text-ink-3">
          {connection.display_name && <span className="font-medium text-ink">{connection.display_name}</span>}
          {connection.connected_at && ` · since ${when(connection.connected_at)}`}
          {connection.problem && <span className="block text-critical-ink">{connection.problem}</span>}
        </p>
      )}

      <div className="mt-auto flex flex-wrap gap-2 pt-1">
        {!isOwner ? (
          <p className="text-xs text-ink-3">Only the business owner can connect apps.</p>
        ) : connected ? (
          <ConfirmButton
            size="sm"
            variant="ghost"
            icon={Unplug}
            question={`Disconnect ${app.name}?`}
            confirmLabel="Disconnect"
            loading={disconnect.isPending}
            onConfirm={() => disconnect.mutate()}
          >
            Disconnect
          </ConfirmButton>
        ) : (
          <Button variant="primary" size="sm" icon={Plug} loading={connect.isPending} onClick={() => connect.mutate()}>
            {connection ? 'Reconnect' : 'Connect'}
          </Button>
        )}
      </div>
    </Card>
  )
}

function ComingSoon() {
  return (
    <div>
      <PageHeader />
      <Card className="mx-auto mt-4 max-w-xl p-6 text-center">
        <Plug className="mx-auto mb-3 size-8 text-ink-3" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-ink">Connecting your apps is coming soon</h2>
        <p className="mt-2 text-sm text-ink-2">
          Linking Instagram, Facebook, WhatsApp and Google needs approval from those companies, and we have applied. Until then you can still
          bring enquiries in by forwarding Justdial, Practo or IndiaMART lead emails, using your website form, or importing a list. Posts
          are posted by you: copy the caption, post it, then tap "Mark as posted".
        </p>
      </Card>
    </div>
  )
}

export default function Connections() {
  const features = useFeatures()
  return features.on('connect_apps') ? <ConnectionsPage /> : <ComingSoon />
}

function ConnectionsPage() {
  const { business } = useBusiness()
  const businessId = business?.id
  const [params, setParams] = useSearchParams()
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60_000 })
  const setup = useQuery({ queryKey: ['connections', 'setup'], queryFn: api.connectionSetup, staleTime: 5 * 60_000 })
  const list = useQuery({
    queryKey: ['connections', businessId],
    queryFn: () => api.connections(businessId),
    enabled: Boolean(businessId),
  })

  const role = me.data?.user?.role
  const isOwner = role === 'owner' || role === 'admin'
  const welcome = params.get('welcome')
  const justConnected = params.get('connected')
  const problem = params.get('error')
  const clear = () => setParams({}, { replace: true })
  const practice = setup.data && Object.values(setup.data.platforms ?? {}).some((p) => p.mode === 'mock')

  // The newest connection per platform (a reconnect adds a new one).
  const byPlatform = {}
  for (const c of list.data ?? []) byPlatform[c.platform] = c

  return (
    <div className="space-y-6">
      <PageHeader />

      {welcome && (
        <Banner tone="brand" icon={CheckCircle2} onClose={clear}>
          <p className="font-semibold">Your account is ready. Last step: connect your apps.</p>
          <p className="mt-1">
            Connect the apps your business uses. You can skip this and come back any time from <b>Connected apps</b> in the menu.
          </p>
        </Banner>
      )}
      {justConnected && (
        <Banner tone="good" icon={CheckCircle2} onClose={clear}>
          Connected: <b>{justConnected}</b>
        </Banner>
      )}
      {problem && (
        <Banner tone="critical" icon={Info} onClose={clear}>
          Not connected: {problem}
        </Banner>
      )}

      <Banner tone="brand" icon={ShieldCheck}>
        <p className="font-semibold">How we know it's your business</p>
        <p className="mt-1">
          Each Connect button opens the app's own login page. Only someone who can log in to your business account there can connect it. We
          never see your password.
        </p>
      </Banner>

      {practice && (
        <p className="text-sm text-ink-3">
          <b>Practice mode:</b> the real login pages work once the site is online and approved by Meta and Google. Until then, Connect pretends,
          so you can try everything.
        </p>
      )}

      {list.isError ? (
        <InlineError error={list.error} onRetry={() => list.refetch()} />
      ) : list.isPending || setup.isPending || me.isPending ? (
        <div className="grid gap-4 md:grid-cols-2">
          {APPS.map((a) => (
            <Skeleton key={a.key} className="h-52 rounded-card" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {APPS.map((app) => (
            <AppCard
              key={app.key}
              app={app}
              connection={byPlatform[app.key]}
              mode={setup.data?.platforms?.[app.key]?.mode ?? 'mock'}
              isOwner={isOwner}
              businessId={businessId}
              setup={setup.data}
            />
          ))}
        </div>
      )}
    </div>
  )
}
