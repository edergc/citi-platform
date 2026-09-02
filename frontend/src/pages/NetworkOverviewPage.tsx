import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Network, Search } from 'lucide-react'
import { Line, LineChart, ResponsiveContainer } from 'recharts'
import { api } from '@/lib/api'
import type { NetworkLatencySparkline, NetworkPathFleetRow, Site } from '@/types'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TableSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { PerfMeter } from '@/components/ui/perf-meter'
import { StatusChip } from '@/components/ui/status-chip'
import { Pagination } from '@/components/ui/pagination'
import { timeAgo } from '@/lib/format'
import { ALL_SITES } from './servers/shared'

const PAGE_SIZE = 20

function LatencySparkline({ points }: { points: { recorded_at: string; latency_ms: number | null }[] }) {
  if (points.length < 2) {
    return <span className="text-xs text-slate-600">—</span>
  }
  return (
    <div className="h-7 w-20">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <Line type="monotone" dataKey="latency_ms" stroke="#38bdf8" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function ReachabilityBadge({ reachable }: { reachable: boolean | null }) {
  if (reachable === null) return <StatusChip tone="neutral">SIN DATOS</StatusChip>
  if (reachable) return <StatusChip tone="ok">RUTA COMPLETA</StatusChip>
  return <StatusChip tone="critical">SIN RESPUESTA</StatusChip>
}

function qualityScoreColor(score: number | null): string {
  if (score == null) return '#475569'
  if (score >= 85) return '#34d399'
  if (score >= 50) return '#fbbf24'
  return '#f87171'
}

function destinationLossColor(percent: number | null): string {
  if (percent == null) return 'text-slate-500'
  if (percent >= 50) return 'text-red-400'
  if (percent > 0) return 'text-amber-400'
  return 'text-slate-400'
}

// Deliberately not a percentage: a técnico who isn't a network specialist reads "67%"
// as "67% packet loss on the connection" no matter what label sits next to it — even
// with an explanation right there. Some intermediate routers just don't answer these
// diagnostic pings (rate-limited or deprioritized on their end); it says nothing about
// whether traffic is actually getting through, unlike the destination column. So this
// collapses to a plain-language, muted label instead of a number — every case says
// something (never a bare dash the técnico has to guess the meaning of), and none of
// the three reads as urgent, since none of them are.
function intermediateHopLabel(row: NetworkPathFleetRow): string {
  if (row.hop_count == null || row.hop_count <= 1) return 'Directo'
  if (row.intermediate_max_loss_percent) return 'Normal'
  return 'OK'
}

function intermediateHopTitle(row: NetworkPathFleetRow): string | undefined {
  if (row.reachable == null) return undefined
  if (row.hop_count == null || row.hop_count <= 1) return 'La ruta llega a Core en un solo salto, sin routers intermedios de por medio.'
  if (row.intermediate_max_loss_percent) {
    return 'Uno o más routers intermedios no siempre responden a estas pruebas de diagnóstico — no afecta la conexión real del servidor.'
  }
  return 'Todos los routers intermedios de la ruta respondieron bien a estas pruebas.'
}

export function NetworkOverviewPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [siteFilter, setSiteFilter] = useState(ALL_SITES)
  const [page, setPage] = useState(1)

  const { data: rows, isLoading, isError } = useQuery({
    queryKey: ['servers', 'network-path-summary'],
    queryFn: async () => (await api.get<NetworkPathFleetRow[]>('/servers/network-path-summary')).data,
    refetchInterval: 60000,
  })

  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
  })

  const { data: sparklines } = useQuery({
    queryKey: ['servers', 'network-path-sparklines'],
    queryFn: async () => (await api.get<NetworkLatencySparkline[]>('/servers/network-path-sparklines', { params: { hours: 6 } })).data,
    refetchInterval: 60000,
  })
  const sparklineByServer = new Map((sparklines ?? []).map((s) => [s.server_id, s.points]))

  const filteredRows = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (rows ?? []).filter((row) => {
      if (siteFilter !== ALL_SITES && row.site_id !== siteFilter) return false
      if (term && !row.hostname.toLowerCase().includes(term)) return false
      return true
    })
  }, [rows, search, siteFilter])

  // Ordenado por Salud ascendente — lo que necesita atención aparece arriba sin tener
  // que ordenar manualmente. Sin datos (null) va al final, no arriba ni mezclado con
  // problemas reales.
  const sortedRows = useMemo(() => {
    return [...filteredRows].sort((a, b) => {
      const aScore = a.quality_score ?? 999
      const bScore = b.quality_score ?? 999
      return aScore - bScore || a.hostname.localeCompare(b.hostname)
    })
  }, [filteredRows])

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageRows = sortedRows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  function updateFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value)
      setPage(1)
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="flex items-center gap-2 text-lg font-medium text-slate-100">
          <Network className="h-5 w-5" /> Diagnóstico de red
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          Estado de la ruta hacia Core para cada servidor de tus sedes — actualizado cada ~60s por cada agente.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input
            placeholder="Buscar por hostname…"
            value={search}
            onChange={(e) => updateFilter(setSearch)(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={siteFilter} onValueChange={updateFilter(setSiteFilter)}>
          <SelectTrigger className="sm:w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_SITES}>Todas las sedes</SelectItem>
            {sites?.map((site) => (
              <SelectItem key={site.id} value={site.id}>
                {site.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && <TableSkeleton rows={8} cols={9} />}
      {isError && <ErrorMessage>No se pudo cargar el diagnóstico de red.</ErrorMessage>}
      {rows && rows.length === 0 && <p className="text-sm text-slate-400">Todavía no hay servidores registrados.</p>}
      {rows && rows.length > 0 && sortedRows.length === 0 && (
        <p className="text-sm text-slate-500">Ningún servidor coincide con los filtros aplicados.</p>
      )}

      {pageRows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Estado</th>
                <th className="px-4 py-2 font-medium">Salud</th>
                <th className="px-4 py-2 font-medium">Servidor</th>
                <th className="px-4 py-2 font-medium">Saltos</th>
                <th className="px-4 py-2 font-medium">Latencia al destino</th>
                <th className="px-4 py-2 font-medium">Pérdida al destino</th>
                <th className="px-4 py-2 font-medium">Saltos intermedios</th>
                <th className="px-4 py-2 font-medium">Tendencia (6h)</th>
                <th className="px-4 py-2 font-medium">Actualizado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {pageRows.map((row) => (
                <tr
                  key={row.server_id}
                  className="cursor-pointer hover:bg-slate-900/40"
                  onClick={() => navigate(`/servers/${row.server_id}`)}
                >
                  <td className="px-4 py-2">
                    <ReachabilityBadge reachable={row.reachable} />
                  </td>
                  <td className="px-4 py-2">
                    <PerfMeter
                      value={row.quality_score}
                      display={row.quality_score != null ? String(row.quality_score) : undefined}
                      color={qualityScoreColor(row.quality_score)}
                      className="max-w-[100px]"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <p className="font-medium text-slate-100">{row.hostname}</p>
                    <p className="text-xs text-slate-500">{row.site_name ?? '—'}</p>
                  </td>
                  <td className="px-4 py-2 text-slate-400">{row.hop_count ?? '—'}</td>
                  <td className="px-4 py-2 text-slate-300">
                    {row.final_latency_ms != null ? `${row.final_latency_ms.toFixed(1)} ms` : '—'}
                  </td>
                  <td className={`px-4 py-2 ${destinationLossColor(row.destination_loss_percent)}`}>
                    {row.destination_loss_percent != null ? `${row.destination_loss_percent.toFixed(0)}%` : '—'}
                  </td>
                  <td className="px-4 py-2 text-slate-500" title={intermediateHopTitle(row)}>
                    {row.reachable == null ? '—' : intermediateHopLabel(row)}
                  </td>
                  <td className="px-4 py-2">
                    <LatencySparkline points={sparklineByServer.get(row.server_id) ?? []} />
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">
                    {row.recorded_at ? timeAgo(row.recorded_at) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {sortedRows.length > 0 && (
        <div className="mt-4 flex flex-col items-center gap-3 sm:flex-row sm:justify-between">
          <p className="text-xs text-slate-500">
            Mostrando {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, sortedRows.length)} de{' '}
            {sortedRows.length} {sortedRows.length === 1 ? 'servidor' : 'servidores'}
          </p>
          <Pagination page={currentPage} totalPages={totalPages} onPageChange={setPage} />
        </div>
      )}

      <p className="mt-4 text-xs text-slate-500">
        "Saltos intermedios: Normal" quiere decir que algún router en el camino (no el servidor ni Core) no siempre
        contesta estas pruebas de diagnóstico — es un comportamiento común de esos equipos, no una falla. Lo que sí
        indica un problema real es "Pérdida al destino" o el estado "Sin respuesta".
      </p>
    </div>
  )
}
