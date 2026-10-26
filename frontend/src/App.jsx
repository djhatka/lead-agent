/*
  The app's root. Not logged in → the login page (or "Create an account").
  Logged in → the router, which picks the page to show inside the app shell
  (see routes.jsx). Logging out (or the login expiring) brings the login
  page back by itself.
*/
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, useSyncExternalStore } from 'react'
import { RouterProvider } from 'react-router'

import { auth } from '@/api/client'
import Login from '@/pages/Login'
import Signup from '@/pages/Signup'
import { router } from '@/routes'

export default function App() {
  const token = useSyncExternalStore(auth.subscribe, auth.snapshot)
  const queryClient = useQueryClient()
  const [screen, setScreen] = useState('login')

  // A different person may log in next: forget everything fetched for the last one.
  useEffect(() => {
    if (!token) queryClient.clear()
  }, [token, queryClient])

  if (token) return <RouterProvider router={router} />
  return screen === 'signup' ? <Signup onLogin={() => setScreen('login')} /> : <Login onSignup={() => setScreen('signup')} />
}
