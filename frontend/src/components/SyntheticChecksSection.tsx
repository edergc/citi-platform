import { Link } from 'react-router-dom'
import { Radar } from 'lucide-react'
import type { Service } from '@/types'

/** Compact teaser only — the real grid (status per sede + uptime %) lives on the
 * dedicated /sinteticos page now, same "one page, everything" pattern as Problemas and
 * Mantenimiento. This just tells whoever's configuring services here that the URL
 * they just set is being watched, and where to go see it. */
export function SyntheticChecksSection({ services }: { services: Service[] }) {
  const monitored = services.filter((s) => s.health_check_url)
  if (monitored.length === 0) return null

  return (
    <Link
      to="/sinteticos"
      className="mt-8 flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 text-sm hover:border-sky-700/60"
    >
      <span className="flex items-center gap-2 text-slate-300">
        <Radar className="h-4 w-4 text-sky-400" />
        {monitored.length} {monitored.length === 1 ? 'servicio' : 'servicios'} con chequeo sintético configurado
      </span>
      <span className="text-sky-400">Ver en Sintéticos →</span>
    </Link>
  )
}
