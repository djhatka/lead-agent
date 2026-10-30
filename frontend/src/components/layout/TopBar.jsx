/*
  The bar above every page: which business you're looking at (switcher),
  two small status pills (sample data, practice AI) and Log out. The theme switch
  sits here on big screens; on phones it's under "More".
*/
import { LogOut } from 'lucide-react'

import { auth } from '@/api/client'
import { BusinessSwitcher } from '@/components/layout/BusinessSwitcher'
import { AiModePill, SamplePill } from '@/components/layout/StatusPills'
import { Button } from '@/components/ui/Button'
import { LanguageToggle } from '@/components/ui/LanguageToggle'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { useLanguage } from '@/hooks/useLanguage'

export function TopBar() {
  const { t } = useLanguage()
  return (
    <header className="sticky top-0 z-30 border-b border-line/60 bg-canvas/75 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-2 px-4 sm:px-6">
        <BusinessSwitcher className="mr-auto" />
        <SamplePill />
        <AiModePill />
        <div className="ml-1 hidden lg:flex lg:items-center lg:gap-2">
          <LanguageToggle />
          <ThemeToggle />
        </div>
        <Button variant="ghost" size="icon" icon={LogOut} aria-label={t('common.logout')} title={t('common.logout')} onClick={() => auth.logout()} />
      </div>
    </header>
  )
}
