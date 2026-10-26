/*
  Which business you're looking at, in the top bar. There's no login yet,
  so this is how you move between the demo businesses (1 = gym,
  2 = car detailing, 3 = dental clinic).

  Switching keeps you on the same page (a lead's drawer closes, since that
  lead belongs to the other business).
*/
import clsx from 'clsx'
import { Car, Check, ChevronsUpDown, Dumbbell, Scissors, Stethoscope, Store, UtensilsCrossed } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router'

import { Popover } from '@/components/ui/Popover'
import { Skeleton } from '@/components/ui/Skeleton'
import { useBusiness } from '@/hooks/useBusiness'
import { useSampleAreas } from '@/hooks/useSampleAreas'

const CATEGORY_ICONS = {
  gym: Dumbbell,
  car_detailing: Car,
  dental_clinic: Stethoscope,
  clinic: Stethoscope,
  salon: Scissors,
  restaurant: UtensilsCrossed,
}

function BusinessMark({ business, className }) {
  const Icon = CATEGORY_ICONS[business.category] ?? Store
  return (
    <span className={clsx('flex shrink-0 items-center justify-center rounded-control bg-brand-soft text-brand', className)}>
      <Icon aria-hidden className="size-[18px]" />
    </span>
  )
}

const place = (b) => [b.area, b.city].filter(Boolean).join(', ')

export function BusinessSwitcher({ className }) {
  const { business, businesses, setBusiness, query } = useBusiness()
  const sample = useSampleAreas().includes('businesses')
  const navigate = useNavigate()
  const location = useLocation()

  if (query.isPending) {
    return (
      <div className={clsx('flex items-center gap-2.5 px-2', className)}>
        <Skeleton className="size-9" />
        <div className="space-y-1.5">
          <Skeleton className="h-3.5 w-32" />
          <Skeleton className="h-3 w-24" />
        </div>
      </div>
    )
  }
  if (!business) return null

  function choose(id, close) {
    close()
    if (id === business.id) return
    setBusiness(id)
    if (location.pathname.startsWith('/leads/')) navigate({ pathname: '/leads', search: location.search })
  }

  return (
    <Popover
      label="Switch business"
      role="menu"
      className={clsx('min-w-0', className)}
      button={
        <span className="flex min-w-0 items-center gap-2.5 rounded-control py-1 pr-2 pl-1 transition-colors hover:bg-surface-sunken">
          <BusinessMark business={business} className="size-9" />
          <span className="min-w-0 leading-tight">
            <span className="block truncate text-sm font-semibold text-ink">{business.name}</span>
            <span className="block truncate text-xs text-ink-3">
              {business.category_label ?? business.category}
              {place(business) && ` · ${place(business)}`}
            </span>
          </span>
          <ChevronsUpDown aria-hidden className="size-4 shrink-0 text-ink-3" />
        </span>
      }
    >
      {(close) => (
        <>
          <p className="px-2.5 pt-1.5 pb-1 text-xs font-medium text-ink-3">Switch business</p>
          {businesses.map((b) => {
            const active = b.id === business.id
            return (
              <button
                key={b.id}
                type="button"
                role="menuitemradio"
                aria-checked={active}
                onClick={() => choose(b.id, close)}
                className={clsx(
                  'flex w-full cursor-pointer items-center gap-2.5 rounded-control px-2.5 py-2 text-left transition-colors',
                  active ? 'bg-brand-soft' : 'hover:bg-surface-sunken',
                )}
              >
                <BusinessMark business={b} className="size-8" />
                <span className="min-w-0 flex-1 leading-tight">
                  <span className="block truncate text-sm font-medium text-ink">{b.name}</span>
                  <span className="block truncate text-xs text-ink-3">{b.category_label ?? b.category}</span>
                </span>
                {active && <Check aria-hidden className="size-4 shrink-0 text-brand" />}
              </button>
            )
          })}
          {sample && (
            <p className="mt-1 border-t border-line px-2.5 pt-2 pb-1 text-xs text-ink-3">
              Demo businesses. The server doesn't list businesses yet, so its own data is shown as business 2.
            </p>
          )}
        </>
      )}
    </Popover>
  )
}
