import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Radar } from 'lucide-react'
import { api } from '@/lib/api'
import type { Server, Site, SyntheticCheckSummary, SyntheticOverallStatus, SyntheticProberStatus } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { TableSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { HexagonStat, HexagonLegend } from '@/components/ui/hexagon-stat'
import { GaugeCircle } from '@/components/ui/gauge-circle'
import { StatusChip } from '@/components/ui/status-chip'
import { cn } from '@/lib/utils'
import { timeAgo } from '@/lib/format'

const statusColor: Record<SyntheticOverallStatus, string> = {
  up: '#34d399',
  degraded: '#fbbf24',
  down: '#f87171',
  unknown: '#475569',
}
const statusBadge: Record<SyntheticOverallStatus, { text: string; variant: 'ok' | 'warning' | 'critical' }> = {
  up: { text: 'Service: OK', variant: 'ok' },
  degraded: { text: 'Service: WARN', variant: 'warning' },
  down: { text: 'Service: CRIT', variant: 'critical' },
  unknown: { text: 'Sin datos', variant: 'warning' },
}
const statusBorder: Record<SyntheticOverallStatus, string> = {
  up: 'border-l-emerald-400',
  degraded: 'border-l-amber-400',
  down: 'border-l-red-400',
  unknown: 'border-l-slate-600',
}

function ProberTile({ prober, siteName }: { prober: SyntheticProberStatus; siteName: string | undefined }) {
  return (
    <div
      className={cn(
        'flex min-w-[150px] flex-1 flex-col gap-1 rounded-lg border px-3 py-2',
        prober.success ? 'border-emerald-800 bg-emerald-950/30' : 'border-red-800 bg-red-950/30',
      )}
      title={prober.error_message ?? undefined}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium text-slate-100">{siteName ?? prober.prober_hostname ?? 'sonda eliminada'}</span>
        <StatusChip tone={prober.success ? 'ok' : 'critical'}>{prober.success ? 'OK' : 'FALLA'}</StatusChip>
      </div>
      <p className="truncate text-xs text-slate-500">{prober.prober_hostname}</p>
      <div className="flex items-center gap-2 text-xs text-slate-400">
        {prober.status_code != null && <span>{prober.status_code}</span>}
        {prober.latency_ms != null && <span>{Math.round(prober.latency_ms)}ms</span>}
        {prober.uptime_percent != null && <span>· {prober.uptime_percent}% 7d</span>}
      </div>
      <p className="text-[11px] text-slate-600">{timeAgo(prober.checked_at)}</p>
    </div>
  )
}

function CheckCard({ summary, siteNameByServerId }: { summary: SyntheticCheckSummary; siteNameByServerId: Map<string, string> }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const runNow = useMutation({
    mutationFn: async () => api.post('/synthetic-checks/run', null, { params: { service_id: summary.service_id } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['synthetic-checks', 'summary'] })
      queryClient.invalidateQueries({ queryKey: ['synthetic-checks', 'results'] })
    },
  })

  return (
    <Card className={cn('border-l-4', statusBorder[summary.overall_status])}>
      <CardContent className="py-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4">
            <GaugeCircle
              size={100}
              value={summary.uptime_percent}
              color={statusColor[summary.overall_status]}
              label="disponib. 7d"
              badge={statusBadge[summary.overall_status]}
            />
            <div className="min-w-0 pt-1">
              <button
                className="truncate text-left text-sm font-medium text-slate-100 hover:text-amber-300"
                onClick={() => navigate(`/systems/${summary.system_id}`)}
              >
                {summary.service_name}
              </button>
              <p className="truncate text-xs text-slate-500">{summary.system_name}</p>
              <p className="mt-1 truncate font-mono text-xs text-slate-600">{summary.health_check_url}</p>
              <p className="mt-1 text-xs text-slate-500">
                {summary.avg_latency_ms != null ? `${Math.round(summary.avg_latency_ms)}ms promedio` : 'sin latencia'}
              </p>
            </div>
          </div>
          <Button size="sm" variant="outline" disabled={runNow.isPending} onClick={() => runNow.mutate()} className="shrink-0">
            {runNow.isPending ? 'Verificando…' : 'Verificar ahora'}
          </Button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {summary.probers.length === 0 ? (
            <p className="text-xs text-slate-500">
              Sin datos aún — se revisa cada 5 min desde cada sonda conectada, o usa "Verificar ahora".
            </p>
          ) : (
            summary.probers.map((p) => (
              <ProberTile
                key={`${summary.service_id}-${p.prober_server_id}`}
                prober={p}
                siteName={p.prober_server_id ? siteNameByServerId.get(p.prober_server_id) : undefined}
              />
            ))
          )}
        </div>
        {runNow.isError && <ErrorMessage className="mt-2 text-xs">No se pudo ejecutar el chequeo.</ErrorMessage>}
      </CardContent>
    </Card>
  )
}

export function SyntheticChecksPage() {
  const { data: summaries, isLoading, isError } = useQuery({
    queryKey: ['synthetic-checks', 'summary'],
    queryFn: async () => (await api.get<SyntheticCheckSummary[]>('/synthetic-checks/summary')).data,
    refetchInterval: 60000,
  })

  const { data: servers } = useQuery({
    queryKey: ['servers'],
    queryFn: async () => (await api.get<Server[]>('/servers')).data,
  })

  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
  })

  const siteNameByServerId = useMemo(() => {
    const siteName = new Map((sites ?? []).map((s) => [s.id, s.name]))
    const map = new Map<string, string>()
    for (const server of servers ?? []) {
      if (server.site_id && siteName.has(server.site_id)) map.set(server.id, siteName.get(server.site_id)!)
    }
    return map
  }, [servers, sites])

  const activeProbeCount = useMemo(
    () => (servers ?? []).filter((s) => s.is_synthetic_probe && s.status === 'online').length,
    [servers],
  )

  const statusCounts = useMemo(() => {
    const counts: Record<SyntheticOverallStatus, number> = { up: 0, degraded: 0, down: 0, unknown: 0 }
    for (const s of summaries ?? []) counts[s.overall_status]++
    return counts
  }, [summaries])

  return (
    <div>
      <div className="mb-6">
        <h2 className="flex items-center gap-2 text-xl font-semibold text-slate-100">
          <Radar className="h-5 w-5 text-sky-400" />
          Chequeos sintéticos
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          Reachability de cada sistema con URL de salud configurada, sondeada en paralelo desde cada sede marcada como sonda
          — detecta problemas de red específicos de una sede que el monitoreo por servidor no ve.
        </p>
      </div>

      <Card className="mb-6">
        <CardContent className="flex flex-wrap items-center gap-6 py-5">
          <HexagonStat
            segments={[
              { value: statusCounts.down, color: statusColor.down, label: 'Caídos' },
              { value: statusCounts.degraded, color: statusColor.degraded, label: 'Degradados' },
              { value: statusCounts.up, color: statusColor.up, label: 'Arriba' },
            ]}
          />
          <HexagonLegend
            segments={[
              { value: statusCounts.down, color: statusColor.down, label: 'Caídos' },
              { value: statusCounts.degraded, color: statusColor.degraded, label: 'Degradados' },
              { value: statusCounts.up, color: statusColor.up, label: 'Arriba' },
            ]}
          />
          <div className="ml-auto text-right">
            <p className="text-3xl font-semibold text-slate-100">{activeProbeCount}</p>
            <p className="text-xs uppercase tracking-wide text-slate-500">sondas activas</p>
          </div>
        </CardContent>
      </Card>

      {isLoading && <TableSkeleton rows={4} cols={5} />}
      {isError && <ErrorMessage>No se pudo cargar el estado de los chequeos sintéticos.</ErrorMessage>}
      {summaries && summaries.length === 0 && (
        <p className="text-sm text-slate-500">
          Ningún servicio tiene una URL de salud configurada todavía. Configúrala en Sistemas → [sistema] → Servicios →
          Editar servicio, y marca al menos un servidor como sonda en Servidores → Editar.
        </p>
      )}

      {summaries && summaries.length > 0 && (
        <div className="flex flex-col gap-3">
          {summaries.map((s) => (
            <CheckCard key={s.service_id} summary={s} siteNameByServerId={siteNameByServerId} />
          ))}
        </div>
      )}
    </div>
  )
}
