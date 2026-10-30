/*
  Sign up: a new owner joins in 3 steps.

    Step 1  Your account    name, email, password
    Step 2  Your business   business name, type, city, area, WhatsApp number
    Step 3  Connect apps    (the "Connected apps" page, opened right after)

  Steps 1 and 2 are sent together (POST /auth/signup): the backend creates
  the account AND the business, starts the 14-day free trial and logs the
  owner in. Step 3 is where the owner proves the business is theirs, by
  logging in to its Instagram / Facebook / WhatsApp / Google on those
  platforms' own pages.
*/
import { ArrowLeft, ArrowRight, Rocket } from 'lucide-react'
import { useState } from 'react'

import { auth } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { router } from '@/routes'
import { useFeatures } from '@/hooks/useFeatures'

const field =
  'mt-1 h-11 w-full rounded-control border border-line bg-surface-raised px-3 text-ink outline-none focus:border-brand'

// The business types the backend knows (backend/app/models.py, INDUSTRIES).
const INDUSTRIES = [
  ['gym', 'Gym or fitness studio'],
  ['salon', 'Salon or spa'],
  ['clinic', 'Clinic (doctor, dentist…)'],
  ['restaurant', 'Restaurant'],
  ['cafe', 'Café'],
  ['coaching', 'Coaching or classes'],
  ['real_estate', 'Real estate'],
  ['auto_service', 'Car service or repair'],
  ['car_detailing', 'Car detailing'],
  ['retail', 'Shop (retail)'],
  ['other', 'Something else'],
]

function Steps({ step, connect = true }) {
  const names = ['Your account', 'Your business', connect ? 'Connect apps' : 'Start']
  return (
    <ol className="mb-5 flex gap-2" aria-label={`Step ${step} of 3`}>
      {names.map((name, i) => (
        <li key={name} className="flex-1">
          <div className={`h-1.5 rounded-full ${i < step ? 'bg-brand' : 'bg-line'}`} />
          <p className={`mt-1.5 text-xs ${i + 1 === step ? 'font-semibold text-ink' : 'text-ink-3'}`}>{name}</p>
        </li>
      ))}
    </ol>
  )
}

export default function Signup({ onLogin }) {
  const features = useFeatures()
  const [step, setStep] = useState(1)
  const [form, setForm] = useState({
    name: '', email: '', password: '',
    business_name: '', industry: '', city: '', area: '', phone: '',
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  function next(e) {
    e.preventDefault()
    setError(null)
    setStep(2)
  }

  async function finish(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const details = {
        ...form,
        email: form.email.trim(),
        name: form.name.trim(),
        business_name: form.business_name.trim(),
        city: form.city.trim() || 'Delhi',
        area: form.area.trim() || null,
        phone: form.phone.trim() || null,
      }
      await auth.signup(details) // logged in: the dashboard appears
      router.navigate(features.on('connect_apps') ? '/settings/connections?welcome=1' : '/') // …on step 3
    } catch (problem) {
      // An email that's already used, or a field the backend didn't accept.
      const message = problem.message ?? 'Something went wrong. Please try again.'
      setError(message)
      if (/email|password|name:/i.test(message) && !/business/i.test(message)) setStep(1)
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-canvas p-4">
      <Card className="w-full max-w-md">
        <p className="font-bold text-ink">Growth Partner</p>
        <h1 className="mt-1 mb-4 text-2xl font-semibold text-ink">Create your account</h1>
        <Steps step={step} connect={features.on('connect_apps')} />

        {step === 1 ? (
          <form onSubmit={next} className="space-y-4">
            <label className="block text-sm font-medium text-ink">
              Your name
              <input required minLength={2} autoComplete="name" value={form.name} onChange={set('name')} className={field} />
            </label>
            <label className="block text-sm font-medium text-ink">
              Email
              <input type="email" required autoComplete="email" value={form.email} onChange={set('email')} className={field} />
            </label>
            <label className="block text-sm font-medium text-ink">
              Password <span className="font-normal text-ink-3">(at least 8 characters)</span>
              <input
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={form.password}
                onChange={set('password')}
                className={field}
              />
            </label>
            {error && (
              <p role="alert" className="rounded-control bg-critical-soft p-3 text-sm text-critical-ink">
                {error}
              </p>
            )}
            <Button type="submit" variant="primary" icon={ArrowRight} className="w-full justify-center">
              Next: your business
            </Button>
          </form>
        ) : (
          <form onSubmit={finish} className="space-y-4">
            <label className="block text-sm font-medium text-ink">
              Business name
              <input required minLength={2} value={form.business_name} onChange={set('business_name')} className={field} placeholder="e.g. Redox Gym" />
            </label>
            <label className="block text-sm font-medium text-ink">
              Type of business
              <select required value={form.industry} onChange={set('industry')} className={field}>
                <option value="" disabled>
                  Choose one
                </option>
                {INDUSTRIES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-sm font-medium text-ink">
                City
                <input value={form.city} onChange={set('city')} className={field} placeholder="Delhi" />
              </label>
              <label className="block text-sm font-medium text-ink">
                Area
                <input value={form.area} onChange={set('area')} className={field} placeholder="e.g. Dwarka" />
              </label>
            </div>
            <label className="block text-sm font-medium text-ink">
              Business WhatsApp number <span className="font-normal text-ink-3">(optional)</span>
              <input type="tel" inputMode="tel" value={form.phone} onChange={set('phone')} className={field} placeholder="98100 00000" />
            </label>
            <p className="text-xs text-ink-3">
              {features.on('connect_apps')
                ? "Next you'll connect your Instagram, Facebook, WhatsApp and Google. Logging in to them proves the business is yours."
                : 'Next you land in your dashboard, with a free trial. Connecting Instagram, WhatsApp and Google is coming soon.'}
            </p>
            {error && (
              <p role="alert" className="rounded-control bg-critical-soft p-3 text-sm text-critical-ink">
                {error}
              </p>
            )}
            <div className="flex gap-2">
              <Button type="button" variant="ghost" icon={ArrowLeft} onClick={() => setStep(1)} disabled={busy}>
                Back
              </Button>
              <Button type="submit" variant="primary" icon={Rocket} loading={busy} className="flex-1 justify-center">
                Start my 14-day free trial
              </Button>
            </div>
          </form>
        )}

        <p className="mt-5 text-center text-sm text-ink-2">
          Already have an account?{' '}
          <button type="button" onClick={onLogin} className="cursor-pointer font-medium text-brand hover:underline">
            Log in
          </button>
        </p>
      </Card>
    </main>
  )
}
