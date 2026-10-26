/*
  Card: the frosted-glass box every widget sits in.

  <Card>
    <CardHeader title="Leads by channel" subtitle="Last 30 days" action={<Button …/>} />
    …content…
  </Card>

  `interactive` adds a gentle lift on hover, for cards you can click.
*/
import clsx from 'clsx'

export function Card({ as: Tag = 'section', interactive = false, className, children, ...props }) {
  return (
    <Tag
      className={clsx(
        'glass rounded-card p-5',
        interactive &&
          'cursor-pointer transition-[transform,box-shadow] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-pop',
        className,
      )}
      {...props}
    >
      {children}
    </Tag>
  )
}

export function CardHeader({ title, subtitle, action, className }) {
  return (
    <header className={clsx('mb-4 flex items-start justify-between gap-3', className)}>
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-ink-3">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  )
}
