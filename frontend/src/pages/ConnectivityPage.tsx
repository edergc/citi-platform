import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '@/lib/api'
import type { FleetSummary, ServerConnectivitySummary, Site } from '@/types'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TableSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { Pagination } from '@/components/ui/pagination'
import { HexagonStat, HexagonLegend } from '@/components/ui/hexagon-stat'
import { PerfMeter } from '@/components/ui/perf-meter'
import { StatusChip } from '@/components/ui/status-chip'
import { timeAgo } from '@/lib/format'
import { extractMotivo } from '@/lib/connectivity'
import { ALL_SITES, statusLabel, statusTone } from './servers/shared'

const PAGE_SIZE = 20
const DAY_OPTIONS = [7, 30, 90, 180] as const

function uptimeColor(value: number | null): string {
  if (value == null) return '#475569'
  if (value >= 99) return '#34d399'
  if (value >= 95) return '#fbbf24'
  return '#f87171'
}

const eventLabel: Record<'disconnected' | 'reconnected', string> = {
  disconnected: 'Desconectado',
  reconnected: 'Reconectado',
}
const eventTone: Record<'disconnected' | 'reconnected', 'critical' | 'ok'> = {
  disconnected: 'critical',
  reconnected: 'ok',
}

export function ConnectivityPage() {
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [siteFilter, setSiteFilter] = useState(ALL_SITES)
  const [days, setDays] = useState<number>(30)
  const [page, setPage] = useState(1)

  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
  })

  const { data: summary } = useQuery({
    queryKey: ['servers', 'fleet-summary'],
    queryFn: async () => (await api.get<FleetSummary>('/servers/fleet-summary')).data,
    refetchInterval: 30000,
  })

  const {
    data: rows,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['servers', 'connectivity-summary', days],
    queryFn: async () => (await api.get<ServerConnectivitySummary[]>('/servers/connectivity-summary', { params: { days } })).data,
    refetchInterval: 30000,
  })

  const filteredRows = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (rows ?? []).filter((row) => {
      if (siteFilter !== ALL_SITES && row.site_id !== siteFilter) return false
      if (term && !row.hostname.toLowerCase().includes(term)) return false
      return true
    })
  }, [rows, siteFilter, search])

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageRows = filteredRows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  function updateFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value)
      setPage(1)
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-slate-100">Conectividad de la flota</h2>
        <p className="mt-1 text-sm text-slate-400">
          Estado actual de cada servidor. Haz clic en uno para ver su historial de desconexiones/reconexiones con fecha, hora y motivo.
        </p>
      </div>

      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-center gap-6 py-5">
          <HexagonStat
            segments={[
              { value: summary?.status_counts.offline ?? 0, color: '#f87171', label: 'Desconectados' },
              { value: summary?.status_counts.degraded ?? 0, color: '#fbbf24', label: 'Degradados' },
              { value: summary?.status_counts.unknown ?? 0, color: '#64748b', label: 'Sin agente / desconocido' },
              { value: summary?.status_counts.online ?? 0, color: '#34d399', label: 'En línea' },
            ]}
          />
          <HexagonLegend
            segments={[
              { value: summary?.status_counts.offline ?? 0, color: '#f87171', label: 'Desconectados' },
              { value: summary?.status_counts.degraded ?? 0, color: '#fbbf24', label: 'Degradados' },
              { value: summary?.status_counts.unknown ?? 0, color: '#64748b', label: 'Sin agente / desconocido' },
              { value: summary?.status_counts.online ?? 0, color: '#34d399', label: 'En línea' },
            ]}
          />
        </CardContent>
      </Card>

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
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
        <Select value={String(days)} onValueChange={updateFilter((v: string) => setDays(Number(v)))}>
          <SelectTrigger className="sm:w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DAY_OPTIONS.map((d) => (
              <SelectItem key={d} value={String(d)}>
                Últimos {d} días
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && <TableSkeleton rows={8} cols={6} />}
      {isError && <ErrorMessage>No se pudo cargar el resumen de conectividad.</ErrorMessage>}
      {rows && rows.length > 0 && filteredRows.length === 0 && (
        <p className="text-sm text-slate-500">Ningún servidor coincide con los filtros aplicados.</p>
      )}

      {pageRows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Estado</th>
                <th className="px-4 py-2 font-medium">Servidor</th>
                <th className="px-4 py-2 font-medium">Sede</th>
                <th className="px-4 py-2 font-medium">Disponibilidad ({days}d)</th>
                <th className="px-4 py-2 font-medium">Interrupciones</th>
                <th className="px-4 py-2 font-medium">Último evento</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {pageRows.map((row) => {
                const motivo = row.last_event_message ? extractMotivo(row.last_event_message) : null
                return (
                  <tr
                    key={row.server_id}
                    className="cursor-pointer hover:bg-slate-900/40"
                    onClick={() => navigate(`/connectivity/${row.server_id}`)}
                  >
                    <td className="px-4 py-2">
                      <StatusChip tone={statusTone[row.status]}>{statusLabel[row.status].toUpperCase()}</StatusChip>
                    </td>
                    <td className="px-4 py-2 font-medium text-slate-100">{row.hostname}</td>
                    <td className="px-4 py-2 text-slate-400">{row.site_name ?? '—'}</td>
                    <td className="px-4 py-2">
                      <PerfMeter
                        value={row.uptime_percent}
                        display={row.uptime_percent != null ? `${row.uptime_percent.toFixed(2)}%` : undefined}
                        color={uptimeColor(row.uptime_percent)}
                        className="max-w-[140px]"
                      />
                    </td>
                    <td className="px-4 py-2 text-slate-400">{row.outage_count}</td>
                    <td className="px-4 py-2">
                      {row.last_event_type ? (
                        <div className="flex flex-col gap-0.5">
                          <div className="flex items-center gap-2">
                            <StatusChip tone={eventTone[row.last_event_type]}>{eventLabel[row.last_event_type].toUpperCase()}</StatusChip>
                            <span className="text-xs text-slate-500">{timeAgo(row.last_event_at)}</span>
                          </div>
                          {motivo && <span className="text-xs text-slate-500">{motivo}</span>}
                        </div>
                      ) : (
                        <span className="text-slate-600">Sin eventos en el periodo</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {filteredRows.length > 0 && (
        <div className="mt-4 flex flex-col items-center gap-3 sm:flex-row sm:justify-between">
          <p className="text-xs text-slate-500">
            Mostrando {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filteredRows.length)} de{' '}
            {filteredRows.length} {filteredRows.length === 1 ? 'servidor' : 'servidores'}
          </p>
          <Pagination page={currentPage} totalPages={totalPages} onPageChange={setPage} />
        </div>
      )}
    </div>
  )
}
