import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, useNavigate } from 'react-router-dom'
import { ArrowDown, ArrowUp, Wrench } from 'lucide-react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import type { FleetConnectivityEvent, FleetDashboard, OsComparison, SiteRanking, TopOffender } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { HexagonStat } from '@/components/ui/hexagon-stat'
import { GaugeCircle } from '@/components/ui/gauge-circle'
import { PerfMeter } from '@/components/ui/perf-meter'
import { StatusChip } from '@/components/ui/status-chip'
import { cn } from '@/lib/utils'
import { timeAgo, timeUntil } from '@/lib/format'

const RECENT_CONNECTIVITY_LIMIT = 8

const eventLabel: Record<FleetConnectivityEvent['event_type'], string> = {
  disconnected: 'Desconectado',
  reconnected: 'Reconectado',
}
const eventTone: Record<FleetConnectivityEvent['event_type'], 'critical' | 'ok'> = {
  disconnected: 'critical',
  reconnected: 'ok',
}

function scoreText(value: number | null): string {
  return value != null ? value.toFixed(0) : '—'
}

function scoreColor(value: number | null): string {
  if (value == null) return 'text-slate-500'
  if (value >= 85) return 'text-slate-400'
  if (value >= 50) return 'text-amber-400'
  return 'text-red-400'
}

function HealthBar({ ok, warning, critical }: { ok: number; warning: number; critical: number }) {
  const total = ok + warning + critical
  if (total === 0) return <div className="h-1.5 w-full rounded-full bg-slate-800" />
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
      {critical > 0 && <div className="bg-red-400" style={{ width: `${(critical / total) * 100}%` }} />}
      {warning > 0 && <div className="bg-amber-400" style={{ width: `${(warning / total) * 100}%` }} />}
      {ok > 0 && <div className="bg-emerald-400" style={{ width: `${(ok / total) * 100}%` }} />}
    </div>
  )
}

function utilizationColor(value: number | null): string {
  if (value == null) return '#475569'
  if (value >= 90) return '#f87171'
  if (value >= 70) return '#fbbf24'
  return '#34d399'
}

function uptimeColor(value: number | null): string {
  if (value == null) return '#475569'
  if (value < 95) return '#f87171'
  if (value < 99) return '#fbbf24'
  return '#34d399'
}

const osLabel: Record<string, string> = { windows: 'Windows', linux: 'Linux' }

function OsCard({ os }: { os: OsComparison }) {
  return (
    <div className="flex-1 rounded-lg border border-slate-800 bg-slate-950/40 p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-medium text-slate-100">{osLabel[os.os_type] ?? os.os_type}</p>
        <p className="text-xs text-slate-500">
          {os.server_count} {os.server_count === 1 ? 'servidor' : 'servidores'}
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-around gap-4">
        <HexagonStat
          size={100}
          segments={[
            { value: os.critical_count, color: '#f87171', label: 'Crítico' },
            { value: os.warning_count, color: '#fbbf24', label: 'Atención' },
            { value: os.ok_count, color: '#34d399', label: 'Bien' },
          ]}
        />
        <GaugeCircle size={100} value={os.avg_cpu_percent} color={utilizationColor(os.avg_cpu_percent)} label="CPU" />
        <GaugeCircle size={100} value={os.avg_ram_percent} color={utilizationColor(os.avg_ram_percent)} label="RAM" />
        <GaugeCircle
          size={100}
          value={os.avg_uptime_percent}
          color={uptimeColor(os.avg_uptime_percent)}
          label="Disponibilidad"
        />
      </div>
    </div>
  )
}

type SortKey = 'server_count' | 'avg_cpu_percent' | 'avg_ram_percent' | 'avg_uptime_percent' | 'avg_network_score' | 'open_alerts'

function OffenderList({
  title,
  unit,
  items,
  colorFn = utilizationColor,
}: {
  title: string
  unit: string
  items: TopOffender[]
  colorFn?: (value: number | null) => string
}) {
  const navigate = useNavigate()
  const isPercent = unit === '%'
  return (
    <Card>
      <CardContent className="py-4">
        <h3 className="mb-3 text-sm font-medium text-slate-200">{title}</h3>
        {items.length === 0 && <p className="text-sm text-slate-500">Sin datos.</p>}
        <div className="flex flex-col divide-y divide-slate-800">
          {items.map((item) => (
            <button
              key={item.server_id}
              onClick={() => navigate(`/servers/${item.server_id}`)}
              className="flex items-center gap-3 py-2 text-left hover:text-amber-300"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-slate-200">{item.hostname}</p>
                {item.site_name && <p className="truncate text-xs text-slate-500">{item.site_name}</p>}
              </div>
              {isPercent ? (
                <PerfMeter value={item.value} color={colorFn(item.value)} className="w-20 shrink-0" />
              ) : (
                <span className="shrink-0 text-sm font-medium text-slate-100">
                  {item.value.toFixed(0)}
                  {unit}
                </span>
              )}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function FleetDashboardsPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [sortKey, setSortKey] = useState<SortKey>('avg_uptime_percent')
  const [sortAsc, setSortAsc] = useState(true)

  const { data, isLoading } = useQuery({
    queryKey: ['servers', 'dashboard'],
    queryFn: async () => (await api.get<FleetDashboard>('/servers/dashboard')).data,
    refetchInterval: 60000,
    enabled: !!user?.is_superuser,
  })

  // Same fleet-wide event log as the dedicated /connectivity page, just the latest few
  // rows for an at-a-glance widget here — "Ver todo" sends admins to the full page for
  // filtering/history beyond this.
  const { data: recentConnectivity } = useQuery({
    queryKey: ['servers', 'connectivity-events', 'recent'],
    queryFn: async () =>
      (await api.get<FleetConnectivityEvent[]>('/servers/connectivity-events', { params: { limit: RECENT_CONNECTIVITY_LIMIT } }))
        .data,
    refetchInterval: 30000,
    enabled: !!user?.is_superuser,
  })

  const sortedSites = useMemo(() => {
    if (!data) return []
    const rows = [...data.site_ranking]
    rows.sort((a, b) => {
      const av = a[sortKey] ?? -1
      const bv = b[sortKey] ?? -1
      return sortAsc ? av - bv : bv - av
    })
    return rows
  }, [data, sortKey, sortAsc])

  if (!user?.is_superuser) {
    return <Navigate to="/" replace />
  }

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc((v) => !v)
    } else {
      setSortKey(key)
      setSortAsc(true)
    }
  }

  function SortHeader({ label, sortKeyValue }: { label: string; sortKeyValue: SortKey }) {
    const active = sortKey === sortKeyValue
    return (
      <th className="px-3 py-2 font-medium">
        <button className="flex items-center gap-1 hover:text-slate-200" onClick={() => toggleSort(sortKeyValue)}>
          {label}
          {active && (sortAsc ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
        </button>
      </th>
    )
  }

  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-32 w-full rounded-lg" />
        <Skeleton className="h-72 w-full rounded-lg" />
        <Skeleton className="h-64 w-full rounded-lg" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-base font-medium text-slate-200">Dashboards</h2>
        <p className="text-xs text-slate-500">Análisis agregado de toda la flota — solo administradores.</p>
      </div>

      <Card>
        <CardContent className="py-5">
          <h3 className="mb-3 text-sm font-medium text-slate-200">Windows vs Linux</h3>
          <div className="flex flex-col gap-3 sm:flex-row">
            {data.os_comparison.map((os) => (
              <OsCard key={os.os_type} os={os} />
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="py-5">
          <h3 className="mb-3 text-sm font-medium text-slate-200">Sedes</h3>
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2 font-medium">Sede</th>
                  <SortHeader label="Servidores" sortKeyValue="server_count" />
                  <th className="px-3 py-2 font-medium">Salud</th>
                  <SortHeader label="CPU" sortKeyValue="avg_cpu_percent" />
                  <SortHeader label="RAM" sortKeyValue="avg_ram_percent" />
                  <SortHeader label="Disponibilidad" sortKeyValue="avg_uptime_percent" />
                  <SortHeader label="Red" sortKeyValue="avg_network_score" />
                  <SortHeader label="Alertas abiertas" sortKeyValue="open_alerts" />
                  <th className="px-3 py-2 font-medium">En mantenimiento</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {sortedSites.map((site: SiteRanking) => (
                  <tr
                    key={site.site_id}
                    className="cursor-pointer hover:bg-slate-900/40"
                    onClick={() => navigate(`/servers?site=${site.site_id}&view=lista`)}
                  >
                    <td className="px-3 py-2 font-medium text-slate-100">{site.site_name}</td>
                    <td className="px-3 py-2 text-slate-400">{site.server_count}</td>
                    <td className="px-3 py-2">
                      <div className="w-24">
                        <HealthBar ok={site.ok_count} warning={site.warning_count} critical={site.critical_count} />
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <PerfMeter value={site.avg_cpu_percent} color={utilizationColor(site.avg_cpu_percent)} className="w-20" />
                    </td>
                    <td className="px-3 py-2">
                      <PerfMeter value={site.avg_ram_percent} color={utilizationColor(site.avg_ram_percent)} className="w-20" />
                    </td>
                    <td className="px-3 py-2">
                      <PerfMeter
                        value={site.avg_uptime_percent}
                        color={uptimeColor(site.avg_uptime_percent)}
                        className="w-20"
                      />
                    </td>
                    <td className={cn('px-3 py-2', scoreColor(site.avg_network_score))}>{scoreText(site.avg_network_score)}</td>
                    <td className="px-3 py-2">
                      {site.open_alerts > 0 ? (
                        <StatusChip tone="warning">{site.open_alerts}</StatusChip>
                      ) : (
                        <span className="text-slate-600">0</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {site.servers_in_maintenance > 0 ? (
                        <Badge variant="maintenance">{site.servers_in_maintenance}</Badge>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="py-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="flex items-center gap-1.5 text-sm font-medium text-slate-200">
              <Wrench className="h-4 w-4 text-violet-400" />
              Ventanas de mantenimiento
            </h3>
            <button className="text-xs text-amber-400 hover:text-amber-300" onClick={() => navigate('/mantenimiento')}>
              Ver todo →
            </button>
          </div>
          <div className="mb-4 flex gap-6">
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Activas ahora</p>
              <p className="mt-1 text-xl font-semibold text-violet-400">{data.maintenance.active_count}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Programadas</p>
              <p className="mt-1 text-xl font-semibold text-slate-300">{data.maintenance.scheduled_count}</p>
            </div>
          </div>
          {data.maintenance.active.length === 0 ? (
            <p className="text-sm text-slate-500">Ningún servidor o sede está en mantenimiento ahora mismo.</p>
          ) : (
            <div className="flex flex-col divide-y divide-slate-800">
              {data.maintenance.active.map((item) => (
                <div key={item.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <Badge variant="maintenance">{item.scope_type === 'server' ? 'Servidor' : 'Sede'}</Badge>
                    <span className="truncate text-sm text-slate-200">{item.scope_label}</span>
                    <span className="shrink-0 truncate text-xs text-slate-500">— {item.reason}</span>
                  </div>
                  <span className="shrink-0 text-xs text-slate-400">Termina {timeUntil(item.ends_at)}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {data.alert_trend.length > 1 && (
        <Card>
          <CardContent className="py-5">
            <h3 className="mb-3 text-sm font-medium text-slate-200">Tendencia de alertas (últimas 12 semanas)</h3>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.alert_trend} margin={{ top: 5, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis
                    dataKey="week_start"
                    tickFormatter={(v: string) => new Date(v).toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit' })}
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    stroke="#334155"
                  />
                  <YAxis allowDecimals={false} tick={{ fill: '#64748b', fontSize: 11 }} stroke="#334155" width={30} />
                  <Tooltip
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    labelFormatter={((v: string) => `Semana del ${new Date(v).toLocaleDateString('es-PE')}`) as any}
                    contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="critical" name="Crítico" stroke="#f87171" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="warning" name="Advertencia" stroke="#fbbf24" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="info" name="Informativo" stroke="#38bdf8" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="py-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-medium text-slate-200">Eventos de conectividad recientes</h3>
            <button className="text-xs text-amber-400 hover:text-amber-300" onClick={() => navigate('/connectivity')}>
              Ver todo →
            </button>
          </div>
          {(!recentConnectivity || recentConnectivity.length === 0) && (
            <p className="text-sm text-slate-500">Sin eventos de conectividad registrados.</p>
          )}
          {recentConnectivity && recentConnectivity.length > 0 && (
            <div className="flex flex-col divide-y divide-slate-800">
              {recentConnectivity.map((event) => (
                <button
                  key={event.id}
                  onClick={() => navigate(`/connectivity/${event.server_id}`)}
                  className="flex items-center justify-between gap-3 py-2 text-left hover:text-amber-300"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <StatusChip tone={eventTone[event.event_type]}>{eventLabel[event.event_type]}</StatusChip>
                    <span className="truncate text-sm text-slate-200">{event.hostname}</span>
                    {event.site_name && <span className="shrink-0 text-xs text-slate-500">· {event.site_name}</span>}
                  </div>
                  <div className="flex shrink-0 flex-col items-end">
                    <span className="text-xs text-slate-400">{new Date(event.occurred_at).toLocaleString('es-PE')}</span>
                    <span className="text-[11px] text-slate-600">{timeAgo(event.occurred_at)}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div>
        <h3 className="mb-3 text-sm font-medium text-slate-200">Top ofensores</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <OffenderList title="Peor disponibilidad (30 días)" unit="%" items={data.worst_uptime} colorFn={uptimeColor} />
          <OffenderList title="Peor conectividad (red)" unit="" items={data.worst_network} />
          <OffenderList title="Más alertas (30 días)" unit="" items={data.most_alerts} />
          <OffenderList title="Mayor CPU actual" unit="%" items={data.highest_cpu} />
          <OffenderList title="Mayor RAM actual" unit="%" items={data.highest_ram} />
        </div>
      </div>
    </div>
  )
}
