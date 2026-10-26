/*
  The login page. Shown instead of the dashboard until you log in.

  It sends your email and password to the backend (POST /auth/login). The
  backend answers with a token: the dashboard keeps it in this browser and
  sends it with every request, so you stay logged in until you log out.
*/
import { LogIn } from 'lucide-react'
import { useState } from 'react'

import { auth } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

const field =
  'mt-1 h-11 w-full rounded-control border border-line bg-surface-raised px-3 text-ink outline-none focus:border-brand'

export default function Login({ onSignup }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await auth.login(email.trim(), password) // the app switches to the dashboard by itself
    } catch (problem) {
      setError(problem.message)
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-canvas p-4">
      <Card className="w-full max-w-sm">
        <p className="font-bold text-ink">Growth Partner</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink">Log in</h1>
        <p className="mt-1 text-sm text-ink-2">Your enquiries, posts and reviews in one place.</p>

        <form onSubmit={submit} className="mt-5 space-y-4">
          <label className="block text-sm font-medium text-ink">
            Email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={field}
            />
          </label>
          <label className="block text-sm font-medium text-ink">
            Password
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={field}
            />
          </label>
          {error && (
            <p role="alert" className="rounded-control bg-critical-soft p-3 text-sm text-critical-ink">
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" icon={LogIn} loading={busy} className="w-full justify-center">
            Log in
          </Button>
        </form>

        <p className="mt-5 text-center text-sm text-ink-2">
          New here?{' '}
          <button type="button" onClick={onSignup} className="cursor-pointer font-medium text-brand hover:underline">
            Create an account
          </button>
        </p>

        {import.meta.env.DEV && (
          <p className="mt-4 text-xs text-ink-3">
            Testing on your laptop? Try gym@demo.in / demo1234, or admin@demo.in / admin1234 to see every business.
          </p>
        )}
      </Card>
    </main>
  )
}
