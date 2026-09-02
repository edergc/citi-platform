import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, ShieldAlert, Wrench } from 'lucide-react'
import { api } from '@/lib/api'
import type { AlertEvent, FleetSummary, Server, ServerHealth, SiteAverage } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton, StatCardsSkeleton } from '@/components/ui/skeleton'
import { HealthBadge } from '@/components/HealthBadge'
import { HexagonStat, HexagonLegend } from '@/components/ui/hexagon-stat'
import { StatusChip } from '@/components/ui/status-chip'
import { cn } from '@/lib/utils'
import { timeAgo } from '@/lib/format'

function KpiStrip({ summary }: { summary: FleetSummary }) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-6 py-5">
        <HexagonStat
          segments={[
            { value: summary.status_counts.offline, color: '#f87171', label: 'Desconectados' },
            { value: summary.status_counts.degraded, color: '#fbbf24', label: 'Degradados' },
            { value: summary.status_counts.online, color: '#34d399', label: 'En línea' },
          ]}
        />
        <HexagonLegend
          segments={[
            { value: summary.status_counts.online, color: '#34d399', label: 'En línea' },
            { value: summary.status_counts.degraded, color: '#fbbf24', label: 'Degradados' },
            { value: summary.status_counts.offline, color: '#f87171', label: 'Desconectados' },
          ]}
        />
        <div className="ml-auto flex items-center gap-2">
          <ShieldAlert className={cn('h-4 w-4', summary.breaching_servers.length > 0 ? 'text-amber-400' : 'text-slate-500')} />
          {summary.breaching_servers.length > 0 ? (
            <StatusChip tone="warning">{summary.breaching_servers.length} con alertas activas</StatusChip>
          ) : (
            <span className="text-sm text-slate-500">Sin alertas activas</span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function SiteCard({
  site,
  health,
  onClick,
}: {
  site: SiteAverage
  health: ServerHealth | undefined
  onClick?: () => void
}) {
  const dotClass =
    health === 'critical'
      ? 'bg-red-400'
      : health === 'warning'
        ? 'bg-amber-400'
        : health === 'ok'
          ? 'bg-emerald-400'
          : 'bg-slate-600'

  const content = (
    <>
      <span className="flex items-center gap-2 truncate text-sm font-medium text-slate-100">
        <span className={cn('h-2 w-2 shrink-0 rounded-full', dotClass)} />
        <span className="truncate">{site.site_name ?? 'Sin sede asignada'}</span>
      </span>
      <span className="text-xs text-slate-500">
        {site.server_count} {site.server_count === 1 ? 'servidor' : 'servidores'}
      </span>
    </>
  )

  return site.site_id ? (
    <button
      onClick={onClick}
      className="flex flex-col gap-1 rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-left transition-colors hover:border-amber-500/50"
    >
      {content}
    </button>
  ) : (
    <div className="flex flex-col gap-1 rounded-lg border border-slate-800 bg-slate-950/40 p-3">{content}</div>
  )
}

function ActivityTeaser({ events }: { events: AlertEvent[] | undefined }) {
  return (
    <Card className="h-fit">
      <CardContent className="py-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-medium text-slate-200">Actividad</h3>
          <Link to="/alerts" className="text-xs text-amber-400 hover:text-amber-300">
            Ver todas →
          </Link>
        </div>
        {events && events.length === 0 && <p className="text-sm text-slate-500">Sin alertas registradas.</p>}
        <div className="flex flex-col divide-y divide-slate-800">
          {events?.slice(0, 5).map((event) => (
            <div key={event.id} className="flex items-start justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm text-slate-200">{event.rule_name}</p>
                {event.hostname && <p className="truncate text-xs text-slate-500">{event.hostname}</p>}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <StatusChip tone={event.status === 'open' ? 'warning' : 'ok'}>
                  {event.status === 'open' ? 'ABIERTA' : 'RESUELTA'}
                </StatusChip>
                <span className="text-xs text-slate-500">{timeAgo(event.triggered_at)}</span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function ResumenView() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: summary, isLoading } = useQuery({
    queryKey: ['servers', 'fleet-summary'],
    queryFn: async () => (await api.get<FleetSummary>('/servers/fleet-summary')).data,
    refetchInterval: 20000,
  })

  const { data: events } = useQuery({
    queryKey: ['alert-rules', 'events'],
    queryFn: async () => (await api.get<AlertEvent[]>('/alert-rules/events', { params: { limit: 10 } })).data,
    refetchInterval: 30000,
  })

  // Shares the ['servers'] cache with the Lista tab — no extra request when switching tabs.
  const { data: servers } = useQuery({
    queryKey: ['servers'],
    queryFn: async () => (await api.get<Server[]>('/servers')).data,
  })

  const siteHealth = useMemo(() => {
    const rank: Record<ServerHealth, number> = { ok: 0, warning: 1, critical: 2 }
    const worst = new Map<string, ServerHealth>()
    for (const server of servers ?? []) {
      if (!server.site_id) continue
      const current = worst.get(server.site_id)
      if (!current || rank[server.health] > rank[current]) worst.set(server.site_id, server.health)
    }
    return worst
  }, [servers])

  const acknowledgeEvent = useMutation({
    mutationFn: async (eventId: string) => api.post<AlertEvent>(`/alert-rules/events/${eventId}/acknowledge`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-rules', 'events'] }),
  })

  const unhealthyServers = useMemo(() => {
    const rank: Record<ServerHealth, number> = { critical: 0, warning: 1, ok: 2 }
    return (servers ?? []).filter((s) => s.health !== 'ok').sort((a, b) => rank[a.health] - rank[b.health])
  }, [servers])
  const unacknowledgedEvents = useMemo(
    () => (events ?? []).filter((e) => e.status === 'open' && !e.acknowledged_at),
    [events],
  )
  const unassignedServers = useMemo(() => (servers ?? []).filter((s) => !s.primary_responsible_user_id), [servers])
  const needsAttention = unhealthyServers.length > 0 || unacknowledgedEvents.length > 0 || unassignedServers.length > 0

  if (isLoading || !summary) {
    return (
      <div className="flex flex-col gap-6">
        <StatCardsSkeleton count={4} />
        <Skeleton className="h-48 w-full rounded-lg" />
        <Skeleton className="h-40 w-full rounded-lg" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <KpiStrip summary={summary} />

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-6">
          <Card className={needsAttention ? 'border-amber-500/30 bg-amber-500/5' : 'border-emerald-500/30 bg-emerald-500/5'}>
            <CardContent className="py-5">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="flex items-center gap-1.5 text-sm font-medium text-slate-100">
                  {needsAttention ? (
                    <AlertTriangle className="h-4 w-4 text-amber-400" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  )}
                  {needsAttention ? 'Necesita tu atención' : 'Todo en orden'}
                </h3>
                <Link to="/problemas" className="text-xs text-amber-400 hover:text-amber-300">
                  Ver todo →
                </Link>
              </div>

              {!needsAttention && (
                <p className="text-sm text-slate-400">
                  Ningún servidor tiene alertas sin reconocer, problemas de salud, o falta de responsable asignado.
                </p>
              )}

              <div className="flex flex-col gap-4">
                {unhealthyServers.length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                      {unhealthyServers.length} {unhealthyServers.length === 1 ? 'servidor necesita' : 'servidores necesitan'} revisión
                    </p>
                    <div className="flex flex-col gap-1.5">
                      {unhealthyServers.slice(0, 5).map((server) => (
                        <button
                          key={server.id}
                          onClick={() => navigate(`/servers/${server.id}`)}
                          className="flex flex-wrap items-center gap-2 rounded-md border border-slate-800 bg-slate-950/40 px-3 py-2 text-left hover:border-amber-500/50"
                        >
                          <span className={cn('flex items-center gap-2', server.active_maintenance && 'opacity-60')}>
                            <HealthBadge health={server.health} reasons={server.health_reasons} />
                            <span className="text-sm text-slate-200">{server.hostname}</span>
                          </span>
                          {server.active_maintenance && (
                            <span title="En mantenimiento">
                              <Wrench className="h-3.5 w-3.5 shrink-0 text-violet-400" />
                            </span>
                          )}
                          {server.health_reasons.length > 0 && (
                            <span className="text-xs text-slate-500">{server.health_reasons.join(' · ')}</span>
                          )}
                        </button>
                      ))}
                      {unhealthyServers.length > 5 && (
                        <p className="text-xs text-slate-500">+{unhealthyServers.length - 5} más</p>
                      )}
                    </div>
                  </div>
                )}

                {unacknowledgedEvents.length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                      {unacknowledgedEvents.length} {unacknowledgedEvents.length === 1 ? 'alerta abierta' : 'alertas abiertas'} sin reconocer
                    </p>
                    <div className="flex flex-col gap-1.5">
                      {unacknowledgedEvents.slice(0, 5).map((event) => (
                        <div
                          key={event.id}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-800 bg-slate-950/40 px-3 py-2"
                        >
                          <span className="text-sm text-slate-200">
                            {event.rule_name}
                            {event.hostname && <span className="text-slate-500"> — {event.hostname}</span>}
                          </span>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={acknowledgeEvent.isPending}
                            onClick={() => acknowledgeEvent.mutate(event.id)}
                          >
                            Reconocer
                          </Button>
                        </div>
                      ))}
                      {unacknowledgedEvents.length > 5 && (
                        <p className="text-xs text-slate-500">+{unacknowledgedEvents.length - 5} más</p>
                      )}
                    </div>
                  </div>
                )}

                {unassignedServers.length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                      {unassignedServers.length} {unassignedServers.length === 1 ? 'servidor sin' : 'servidores sin'} responsable asignado
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {unassignedServers.slice(0, 8).map((server) => (
                        <button
                          key={server.id}
                          onClick={() => navigate(`/servers/${server.id}`)}
                          className="rounded-md border border-slate-800 bg-slate-950/40 px-2.5 py-1 text-xs text-slate-300 hover:border-amber-500/50"
                        >
                          {server.hostname}
                        </button>
                      ))}
                      {unassignedServers.length > 8 && (
                        <span className="px-2.5 py-1 text-xs text-slate-500">+{unassignedServers.length - 8} más</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {summary.site_averages.length > 0 && (
            <Card>
              <CardContent className="py-5">
                <h3 className="mb-1 text-sm font-medium text-slate-200">Sedes</h3>
                <p className="mb-3 text-xs text-slate-500">Elige una sede para ver el detalle de sus servidores.</p>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
                  {summary.site_averages.map((site) => (
                    <SiteCard
                      key={site.site_id ?? 'sin-sede'}
                      site={site}
                      health={site.site_id ? siteHealth.get(site.site_id) : undefined}
                      onClick={site.site_id ? () => navigate(`/servers?site=${site.site_id}&view=lista`) : undefined}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        <ActivityTeaser events={events} />
      </div>
    </div>
  )
}
