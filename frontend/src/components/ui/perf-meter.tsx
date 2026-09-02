import { cn } from '@/lib/utils'

/** Checkmk's "Perf-O-Meter" — a compact horizontal bar with the value printed on top of
 * the fill, used inline in tables instead of bare numbers. */
export function PerfMeter({
  value,
  max = 100,
  display,
  color = '#34d399',
  className,
}: {
  value: number | null
  max?: number
  display?: string
  color?: string
  className?: string
}) {
  const fraction = value == null ? 0 : Math.min(1, Math.max(0, value / max))
  return (
    <div className={cn('relative h-5 w-full min-w-[64px] overflow-hidden rounded bg-slate-800', className)}>
      <div className="absolute inset-y-0 left-0 transition-[width] duration-500" style={{ width: `${fraction * 100}%`, backgroundColor: color }} />
      <span className="absolute inset-0 flex items-center justify-center text-[11px] font-medium text-slate-100 mix-blend-difference">
        {display ?? (value != null ? `${value.toFixed(1)}${max === 100 ? '%' : ''}` : '—')}
      </span>
    </div>
  )
}
