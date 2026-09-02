import { cn } from '@/lib/utils'

/** Checkmk's "speedometer" gauge — a 270° arc (90° gap at the bottom), track + colored
 * progress, big number centered, optional status pill underneath. Plain SVG, no chart
 * library: two stacked arcs built from stroke-dasharray, rotated so the gap sits at the
 * bottom like the reference screenshots. */
export function GaugeCircle({
  value,
  max = 100,
  unit = '%',
  color = '#34d399',
  size = 140,
  strokeWidth = 10,
  label,
  badge,
}: {
  value: number | null
  max?: number
  unit?: string
  color?: string
  size?: number
  strokeWidth?: number
  label?: string
  badge?: { text: string; variant: 'ok' | 'warning' | 'critical' }
}) {
  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - strokeWidth
  const circumference = 2 * Math.PI * r
  const sweep = 270
  const trackDash = (sweep / 360) * circumference
  const fraction = value == null ? 0 : Math.min(1, Math.max(0, value / max))
  const progressDash = fraction * trackDash

  const badgeClass = {
    ok: 'bg-emerald-500 text-emerald-950',
    warning: 'bg-amber-500 text-amber-950',
    critical: 'bg-red-500 text-red-950',
  }

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative" style={{ width: size, height: size * 0.86 }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="absolute -top-[7%] left-0">
          <g transform={`rotate(135 ${cx} ${cy})`}>
            <circle
              cx={cx} cy={cy} r={r} fill="none" stroke="#1e293b" strokeWidth={strokeWidth}
              strokeDasharray={`${trackDash} ${circumference}`} strokeLinecap="round"
            />
            <circle
              cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={strokeWidth}
              strokeDasharray={`${progressDash} ${circumference}`} strokeLinecap="round"
              className="transition-[stroke-dasharray] duration-500"
            />
          </g>
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn('font-semibold text-slate-100', size >= 120 ? 'text-2xl' : 'text-lg')}>
            {value != null ? value.toFixed(value < 10 ? 1 : 0) : '—'}
            <span className="text-sm font-normal text-slate-400">{value != null ? unit : ''}</span>
          </span>
        </div>
      </div>
      {badge && (
        <span className={cn('rounded px-2 py-0.5 text-xs font-semibold', badgeClass[badge.variant])}>{badge.text}</span>
      )}
      {label && <span className="text-xs text-slate-500">{label}</span>}
    </div>
  )
}
