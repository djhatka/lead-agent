/*
  The starting point of the dashboard.

  The browser loads index.html, which loads this file. It wraps the whole app in:
  - QueryClientProvider: TanStack Query's shared "memory" of everything
    fetched from the backend, so two pages asking for the same data share
    one request, and data refreshes itself in the background.
  - MotionConfig: animation settings for every Motion component.
*/
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App.jsx'
import './styles/index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // data younger than 30 s is reused without asking the backend again
      retry: 1, // one quiet retry if the backend hiccups
      refetchOnWindowFocus: true, // switching back to the tab refreshes the numbers
    },
  },
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* reducedMotion="user": if the device asks for less motion, Motion skips movement */}
      <MotionConfig reducedMotion="user">
        <App />
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
)
