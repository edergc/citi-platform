import { cn } from '@/lib/utils'

export interface HexagonSegment {
  value: number
  color: string
  label: string
}

/** Checkmk's signature "hexagon donut" — a hexagon-clipped conic-gradient with a
 * hexagon-shaped hole cut out of the middle, total centered inside. Pure CSS
 * (clip-path + conic-gradient), no chart library — the hexagon silhouette is what
 * reads as "Checkmk" at a glance, everything else is a normal donut chart. */
export function HexagonStat({
  segments,
  size = 140,
  emptyLabel = '—',
}: {
  segments: HexagonSegment[]
  size?: number
  emptyLabel?: string
}) {
  const total = segments.reduce((sum, s) => sum + s.value, 0)
  const hexClip = 'polygon(25% 3%, 75% 3%, 100% 50%, 75% 97%, 25% 97%, 0% 50%)'

  let gradient: string
  if (total <= 0) {
    gradient = '#1e293b'
  } else {
    let acc = 0
    const stops: string[] = []
    for (const seg of segments) {
      if (seg.value <= 0) continue
      const start = (acc / total) * 360
      acc += seg.value
      const end = (acc / total) * 360
      stops.push(`${seg.color} ${start}deg ${end}deg`)
    }
    gradient = `conic-gradient(${stops.join(', ')})`
  }

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <div className="absolute inset-0" style={{ clipPath: hexClip, background: gradient }} />
      <div
        className="absolute flex items-center justify-center bg-slate-900"
        style={{ inset: size * 0.16, clipPath: hexClip }}
      >
        <span className={cn('font-semibold text-slate-100', size >= 120 ? 'text-2xl' : 'text-lg')}>
          {total > 0 ? total : emptyLabel}
        </span>
      </div>
    </div>
  )
}

export function HexagonLegend({ segments }: { segments: HexagonSegment[] }) {
  return (
    <div className="flex flex-col gap-1.5">
      {segments.map((s) => (
        <div key={s.label} className="flex items-center gap-2 text-sm">
          <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: s.color }} />
          <span className="tabular-nums font-medium text-slate-100">{s.value}</span>
          <span className="text-slate-400">{s.label}</span>
        </div>
      ))}
    </div>
  )
}
