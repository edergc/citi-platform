import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Cog,
  Cpu,
  Download,
  Gauge,
  HardDrive,
  History,
  KeyRound,
  LayoutDashboard,
  MemoryStick,
  Network,
  NotebookPen,
  Trash2,
  User,
  Wrench,
  XCircle,
} from 'lucide-react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import type {
  AgentStatus,
  AlertRule,
  DiskForecast,
  NetworkPathHistory,
  Server,
  ServerActivityItem,
  ServerEvent,
  ServerMetricHistoryPoint,
  ServerMetrics,
  ServerNote,
  ServerStatus,
  ServerUptimeSummary,
  Service,
  ServiceStatus,
  Site,
} from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { GaugeCircle } from '@/components/ui/gauge-circle'
import { StatusChip } from '@/components/ui/status-chip'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { DetailPageSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { ServerFormDialog } from '@/components/ServerFormDialog'
import { MaintenanceWindowFormDialog } from '@/components/MaintenanceWindowFormDialog'
import { HealthBadge } from '@/components/HealthBadge'
import { ServiceActions } from '@/components/ServiceActions'
import { cn } from '@/lib/utils'
import { formatBytes, formatMBps, formatMbps, formatUptime, timeAgo, timeUntil } from '@/lib/format'

const statusLabel: Record<ServerStatus, string> = {
  online: 'En línea',
  offline: 'Desconectado',
  degraded: 'Degradado',
  unknown: 'Sin datos',
}

const statusTone: Record<ServerStatus, 'ok' | 'critical' | 'warning' | 'neutral'> = {
  online: 'ok',
  offline: 'critical',
  degraded: 'warning',
  unknown: 'neutral',
}

const agentStatusLabel: Record<AgentStatus, string> = {
  pending: 'Pendiente de enrolamiento',
  active: 'Agente activo',
  revoked: 'Agente revocado',
  unreachable: 'Agente sin respuesta',
}

const agentStatusTone: Record<AgentStatus, 'neutral' | 'ok' | 'critical'> = {
  pending: 'neutral',
  active: 'ok',
  revoked: 'critical',
  unreachable: 'critical',
}

const serviceStatusTone: Record<ServiceStatus, 'ok' | 'neutral' | 'warning'> = {
  running: 'ok',
  stopped: 'neutral',
  degraded: 'warning',
  unknown: 'neutral',
}

// Fallbacks only, used when no matching AlertRule exists — the real thresholds are
// admin-configurable (Admin → Alertas) and fetched below so this page never silently
// disagrees with what's actually enforced server-side.
const RAM_WARN = 90
const RAM_CRIT = 96
const CPU_WARN = 85
const CPU_CRIT = 95
const DISK_WARN = 85
const DISK_CRIT = 95

function thresholdsForMetric(
  rules: AlertRule[] | undefined,
  serverId: string | undefined,
  metric: string,
  metricTarget: string | null,
  fallbackWarn: number,
  fallbackCrit: number,
): { warn: number; crit: number } {
  const applicable = (rules ?? []).filter(
    (r) => r.enabled && r.metric === metric && (r.scope_id === null || r.scope_id === serverId),
  )
  const pool = metric === 'disk_percent_used'
    ? (() => {
        const forMount = applicable.filter((r) => r.metric_target === metricTarget)
        return forMount.length > 0 ? forMount : applicable.filter((r) => !r.metric_target)
      })()
    : applicable
  const bySeverity = (severity: string) =>
    pool.filter((r) => r.severity === severity).sort((a, b) => a.threshold - b.threshold)[0]?.threshold
  return {
    warn: bySeverity('warning') ?? fallbackWarn,
    crit: bySeverity('critical') ?? fallbackCrit,
  }
}

function pctColor(pct: number | null | undefined, warn: number, crit: number): string {
  if (pct == null) return 'text-slate-500'
  if (pct >= crit) return 'text-red-400'
  if (pct >= warn) return 'text-amber-400'
  return 'text-emerald-400'
}

function pctColorHex(pct: number | null | undefined, warn: number, crit: number): string {
  if (pct == null) return '#475569'
  if (pct >= crit) return '#f87171'
  if (pct >= warn) return '#fbbf24'
  return '#34d399'
}

function barColor(pct: number | null | undefined, warn: number, crit: number): string {
  if (pct == null) return 'bg-slate-700'
  if (pct >= crit) return 'bg-red-500'
  if (pct >= warn) return 'bg-amber-500'
  return 'bg-emerald-500'
}

type DetailTab = 'resumen' | 'disco' | 'red' | 'servicios' | 'procesos' | 'actividad'

const detailTabs: { key: DetailTab; label: string; icon: typeof Cpu }[] = [
  { key: 'resumen', label: 'Resumen', icon: LayoutDashboard },
  { key: 'disco', label: 'Disco', icon: HardDrive },
  { key: 'red', label: 'Red', icon: Network },
  { key: 'servicios', label: 'Servicios', icon: Cog },
  { key: 'procesos', label: 'Procesos', icon: Activity },
  { key: 'actividad', label: 'Actividad', icon: History },
]

const HISTORY_RANGES: { label: string; hours: number }[] = [
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 24 * 7 },
  { label: '30d', hours: 24 * 30 },
]

function wearoutColor(percent: number | null): string {
  if (percent == null) return 'text-slate-500'
  if (percent >= 90) return 'text-red-400'
  if (percent >= 70) return 'text-amber-400'
  return 'text-emerald-400'
}

function uptimeColor(percent: number): string {
  if (percent >= 99.9) return 'text-emerald-400'
  if (percent >= 99) return 'text-amber-400'
  return 'text-red-400'
}

function formatOutageDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  return formatUptime(seconds)
}

// Cycled per hop index in the network-path latency chart — extends the same palette
// already used elsewhere in the app (CPU/RAM/disk trend lines) with a few more hues,
// since the number of hops varies per server.
const HOP_LINE_COLORS = [
  '#38bdf8', '#a78bfa', '#fb923c', '#2dd4bf', '#fb7185',
  '#facc15', '#4ade80', '#f472b6', '#818cf8', '#fbbf24',
]

function activityTone(item: ServerActivityItem): 'neutral' | 'ok' | 'warning' | 'critical' | 'info' {
  if (item.kind === 'notification') {
    if (item.status === 'critical') return 'critical'
    if (item.status === 'warning') return 'warning'
    return 'info'
  }
  if (item.status === 'success') return 'ok'
  if (item.status === 'failed') return 'critical'
  return 'neutral'
}

function eventLevelLabel(level: number): string {
  if (level === 1) return 'Crítico'
  if (level === 2) return 'Error'
  return `Nivel ${level}`
}

function eventLevelTone(level: number): 'critical' | 'warning' {
  return level === 1 ? 'critical' : 'warning'
}

function activityStatusLabel(item: ServerActivityItem): string {
  const labels: Record<string, string> = {
    critical: 'Crítico',
    warning: 'Advertencia',
    info: 'Informativo',
    success: 'Éxito',
    failed: 'Falló',
    pending: 'Pendiente',
  }
  return labels[item.status] ?? item.status
}

function StatCard({
  icon: Icon,
  label,
  value,
  valueClassName,
  children,
}: {
  icon: typeof Cpu
  label: string
  value: string
  valueClassName?: string
  children?: React.ReactNode
}) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-center gap-2 text-xs uppercase text-slate-500">
          <Icon className="h-3.5 w-3.5" />
          {label}
        </div>
        <div className={cn('mt-1 text-2xl font-semibold', valueClassName ?? 'text-slate-100')}>{value}</div>
        {children}
      </CardContent>
    </Card>
  )
}

function CircularGauge({
  percent,
  size = 76,
  strokeWidth = 8,
  colorClassName,
}: {
  percent: number | null | undefined
  size?: number
  strokeWidth?: number
  colorClassName: string
}) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const clamped = Math.min(Math.max(percent ?? 0, 0), 100)
  const offset = circumference - (clamped / 100) * circumference

  return (
    <svg width={size} height={size} className="-rotate-90" viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={strokeWidth} className="stroke-slate-800" />
      {percent != null && (
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={cn('stroke-current transition-[stroke-dashoffset]', colorClassName)}
        />
      )}
    </svg>
  )
}

function GaugeCard({
  icon: Icon,
  label,
  percent,
  color,
  children,
}: {
  icon: typeof Cpu
  label: string
  percent: number | null | undefined
  color: string
  children?: React.ReactNode
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 py-4">
        <GaugeCircle value={percent ?? null} color={color} size={90} strokeWidth={9} />
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-slate-500">
            <Icon className="h-3.5 w-3.5" />
            {label}
          </p>
          {children}
        </div>
      </CardContent>
    </Card>
  )
}

function InfoField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-0.5 truncate text-sm font-medium text-slate-200" title={value}>
        {value}
      </p>
    </div>
  )
}

const coreUrl = (import.meta.env.VITE_API_URL ?? '').replace(/\/api\/v1\/?$/, '')

export function ServerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user, hasPermission } = useAuth()
  const [enrollToken, setEnrollToken] = useState<string | null>(null)
  const [showManualToken, setShowManualToken] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [detailTab, setDetailTab] = useState<DetailTab>('resumen')

  const { data: server, isLoading } = useQuery({
    queryKey: ['servers', id],
    queryFn: async () => (await api.get<Server>(`/servers/${id}`)).data,
    enabled: !!id,
  })

  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
  })

  const { data: metrics } = useQuery({
    queryKey: ['servers', id, 'metrics'],
    queryFn: async () => (await api.get<ServerMetrics>(`/servers/${id}/metrics`)).data,
    enabled: !!id,
    refetchInterval: 15000,
  })

  const { data: alertRules } = useQuery({
    queryKey: ['alert-rules'],
    queryFn: async () => (await api.get<AlertRule[]>('/alert-rules')).data,
  })

  const [historyHours, setHistoryHours] = useState(24)
  const { data: history } = useQuery({
    queryKey: ['servers', id, 'metrics', 'history', historyHours],
    queryFn: async () =>
      (await api.get<ServerMetricHistoryPoint[]>(`/servers/${id}/metrics/history`, { params: { hours: historyHours } })).data,
    enabled: !!id,
    refetchInterval: 60000,
  })

  const { data: uptime } = useQuery({
    queryKey: ['servers', id, 'uptime'],
    queryFn: async () => (await api.get<ServerUptimeSummary>(`/servers/${id}/uptime`, { params: { days: 30 } })).data,
    enabled: !!id,
    refetchInterval: 60000,
  })

  const { data: diskForecast } = useQuery({
    queryKey: ['servers', id, 'disk-forecast'],
    queryFn: async () => (await api.get<DiskForecast>(`/servers/${id}/disk-forecast`, { params: { days: 14 } })).data,
    enabled: !!id,
    refetchInterval: 60000,
  })

  const { data: services } = useQuery({
    queryKey: ['services', 'server', id],
    queryFn: async () => (await api.get<Service[]>('/services', { params: { server_id: id } })).data,
    enabled: !!id,
    refetchInterval: 60000,
  })
  const portConnectionByPort = new Map((metrics?.port_connections ?? []).map((p) => [p.port, p.connection_count]))

  const { data: networkPath } = useQuery({
    queryKey: ['servers', id, 'network-path'],
    queryFn: async () => (await api.get<NetworkPathHistory>(`/servers/${id}/network-path`, { params: { hours: 6 } })).data,
    enabled: !!id,
    refetchInterval: 60000,
  })

  const networkHopNumbers = networkPath
    ? Array.from(new Set(networkPath.samples.flatMap((s) => s.hops.map((h) => h.hop_number))))
        .sort((a, b) => a - b)
        .slice(0, 15)
    : []

  const networkChartData = (networkPath?.samples ?? []).map((sample) => {
    const point: Record<string, string | number | null> = { recorded_at: sample.recorded_at }
    for (const hop of sample.hops) {
      point[`hop_${hop.hop_number}`] = hop.avg_latency_ms
    }
    return point
  })

  const cpuThresholds = thresholdsForMetric(alertRules, id, 'cpu_percent', null, CPU_WARN, CPU_CRIT)
  const ramThresholds = thresholdsForMetric(alertRules, id, 'ram_percent', null, RAM_WARN, RAM_CRIT)
  const worstDisk = metrics?.disks?.length ? metrics.disks.reduce((a, b) => (a.percent_used >= b.percent_used ? a : b)) : null
  const worstDiskPercent = worstDisk?.percent_used ?? null
  const worstDiskThresholds = thresholdsForMetric(alertRules, id, 'disk_percent_used', worstDisk?.mount ?? null, DISK_WARN, DISK_CRIT)

  const [activityLimit, setActivityLimit] = useState(8)
  const { data: activity } = useQuery({
    queryKey: ['servers', id, 'recent-activity', activityLimit],
    queryFn: async () =>
      (await api.get<ServerActivityItem[]>(`/servers/${id}/recent-activity`, { params: { limit: activityLimit } })).data,
    enabled: !!id,
    refetchInterval: 30000,
  })

  const [notesLimit, setNotesLimit] = useState(10)
  const { data: notes } = useQuery({
    queryKey: ['servers', id, 'notes', notesLimit],
    queryFn: async () => (await api.get<ServerNote[]>(`/servers/${id}/notes`, { params: { limit: notesLimit } })).data,
    enabled: !!id,
  })

  const [eventsLimit, setEventsLimit] = useState(10)
  const { data: events } = useQuery({
    queryKey: ['servers', id, 'events', eventsLimit],
    queryFn: async () => (await api.get<ServerEvent[]>(`/servers/${id}/events`, { params: { limit: eventsLimit } })).data,
    enabled: !!id,
    refetchInterval: 60000,
  })

  const [noteBody, setNoteBody] = useState('')
  const createNote = useMutation({
    mutationFn: async () => api.post<ServerNote>(`/servers/${id}/notes`, { body: noteBody }),
    onSuccess: () => {
      setNoteBody('')
      queryClient.invalidateQueries({ queryKey: ['servers', id, 'notes'] })
    },
  })

  function handleCreateNote(e: FormEvent) {
    e.preventDefault()
    if (!noteBody.trim()) return
    createNote.mutate()
  }

  const deleteServer = useMutation({
    mutationFn: async () => api.delete(`/servers/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['servers'] })
      navigate('/servers')
    },
  })

  const enrollTokenMutation = useMutation({
    mutationFn: async () => (await api.post<{ token: string }>(`/agents/servers/${id}/enroll-token`)).data,
    onSuccess: (data) => setEnrollToken(data.token),
  })

  const downloadInstallerMutation = useMutation({
    mutationFn: async () => api.get(`/agents/servers/${id}/installer`, { responseType: 'blob' }),
    onSuccess: (response) => {
      const isLinux = server?.os_type === 'linux'
      const url = URL.createObjectURL(
        new Blob([response.data], { type: isLinux ? 'application/gzip' : 'application/zip' }),
      )
      const a = document.createElement('a')
      a.href = url
      a.download = `citi-agent-${server?.hostname ?? id}.${isLinux ? 'tar.gz' : 'zip'}`
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  if (isLoading || !server) {
    return <DetailPageSkeleton />
  }

  const siteName = server.site_id ? sites?.find((s) => s.id === server.site_id)?.name : null

  return (
    <div>
      <Link to="/servers" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200">
        <ArrowLeft className="h-4 w-4" /> Servidores
      </Link>

      <Card className="mb-6">
        <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold text-slate-100">{server.hostname}</h2>
              <div className={cn('flex flex-wrap items-center gap-2', server.active_maintenance && 'opacity-60')}>
                <HealthBadge health={server.health} reasons={server.health_reasons} />
                <StatusChip tone={statusTone[server.status]}>{statusLabel[server.status].toUpperCase()}</StatusChip>
                {metrics?.agent_status && (
                  <StatusChip tone={agentStatusTone[metrics.agent_status]}>{agentStatusLabel[metrics.agent_status].toUpperCase()}</StatusChip>
                )}
              </div>
              {server.active_maintenance && (
                <Badge variant="maintenance" title={server.active_maintenance.reason}>
                  En mantenimiento · termina {timeUntil(server.active_maintenance.ends_at)}
                </Badge>
              )}
            </div>
            {server.health !== 'ok' && server.health_reasons.length > 0 && (
              <p className="mt-1.5 text-sm text-slate-400">{server.health_reasons.join(' · ')}</p>
            )}
            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-400">
              {siteName && <span>Sede: {siteName}</span>}
              <span className="inline-flex items-center gap-1">
                <User className="h-3.5 w-3.5" />
                Responsable: {server.primary_responsible_user_name ?? 'Sin asignar'}
              </span>
              {server.ip_address && <span>{server.ip_address}</span>}
              <span>
                {server.os_type} {server.os_version}
              </span>
              <span>Último latido: {timeAgo(metrics?.last_heartbeat_at)}</span>
              {metrics?.uptime_seconds != null && <span>Uptime: {formatUptime(metrics.uptime_seconds)}</span>}
            </div>
            {server.usage_tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {server.usage_tags.map((tag) => (
                  <Badge key={tag} variant="default">
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </div>
          {(hasPermission('servers.manage') || user?.is_superuser) && (
            <div className="flex shrink-0 items-center gap-2">
              {hasPermission('servers.manage') && (
                <MaintenanceWindowFormDialog
                  defaultScope={{ type: 'server', id: server.id, label: server.hostname }}
                  trigger={
                    <Button variant="outline" size="sm">
                      <Wrench className="h-3.5 w-3.5" />
                      Mantenimiento
                    </Button>
                  }
                />
              )}
              {user?.is_superuser && (
                <>
                  <Button
                    size="sm"
                    disabled={downloadInstallerMutation.isPending}
                    onClick={() => downloadInstallerMutation.mutate()}
                  >
                    <Download className="h-3.5 w-3.5" />
                    {downloadInstallerMutation.isPending ? 'Generando…' : 'Descargar instalador'}
                  </Button>
                  <ServerFormDialog server={server} trigger={<Button variant="outline" size="sm">Editar</Button>} />
                  <Button variant="destructive" size="sm" onClick={() => setConfirmDeleteOpen(true)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {user?.is_superuser && (
      <>
      {downloadInstallerMutation.isSuccess && (
        <div className="mb-6 rounded-lg border border-emerald-800 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-200">
          <p className="font-medium">Instalador descargado.</p>
          {server.os_type === 'linux' ? (
            <p className="mt-1 text-emerald-300/90">
              Copia el .tar.gz al servidor nuevo (por ejemplo con WinSCP, o <code className="rounded bg-slate-900 px-1.5 py-0.5 text-xs">scp</code>),
              extráelo (<code className="rounded bg-slate-900 px-1.5 py-0.5 text-xs">tar -xzf citi-agent-*.tar.gz</code>) y
              ejecuta <code className="rounded bg-slate-900 px-1.5 py-0.5 text-xs">sudo ./install.sh</code> dentro de la
              carpeta (por SSH/PuTTY). Solo necesita <code className="rounded bg-slate-900 px-1.5 py-0.5 text-xs">python3</code> —
              las dependencias ya vienen incluidas para no depender de internet; si este servidor tiene una versión de
              Python fuera de lo común, el instalador intenta bajarlas de PyPI como respaldo. Enrola el agente y lo
              registra como servicio de systemd (<code className="rounded bg-slate-900 px-1.5 py-0.5 text-xs">citi-agent</code>) automáticamente.
            </p>
          ) : (
            <p className="mt-1 text-emerald-300/90">
              Copia el .zip al servidor nuevo, extráelo completo y ejecuta{' '}
              <code className="rounded bg-slate-900 px-1.5 py-0.5 text-xs">install.bat</code> (doble clic — se autoeleva a
              Administrador). Ya trae Python incluido: no hay que instalar nada más. Enrola el agente y lo registra como
              servicio de Windows automáticamente.
            </p>
          )}
          <p className="mt-2 text-xs text-emerald-400">
            <a href="/docs/instalar-agente.html" target="_blank" rel="noopener" className="underline hover:text-emerald-300">
              Ver guía detallada
            </a>{' '}
            si prefieres hacerlo paso a paso, o{' '}
            <button className="underline hover:text-emerald-300" onClick={() => setShowManualToken(true)}>
              generar solo el token
            </button>{' '}
            para una instalación manual.
          </p>
          <Button variant="ghost" size="sm" className="mt-2" onClick={() => downloadInstallerMutation.reset()}>
            Cerrar
          </Button>
        </div>
      )}

      {!downloadInstallerMutation.isSuccess && !showManualToken && (
        <p className="mb-6 text-xs text-slate-500">
          ¿Prefieres instalar manualmente?{' '}
          <button className="underline hover:text-slate-300" onClick={() => setShowManualToken(true)}>
            Generar solo el token de enrolamiento
          </button>
          .
        </p>
      )}

      {showManualToken && !downloadInstallerMutation.isSuccess && (
        <div className="mb-6 rounded-lg border border-amber-800 bg-amber-950/40 px-4 py-3 text-sm text-amber-200">
          {!enrollToken && (
            <Button size="sm" disabled={enrollTokenMutation.isPending} onClick={() => enrollTokenMutation.mutate()}>
              <KeyRound className="h-3.5 w-3.5" />
              Generar token de enrolamiento
            </Button>
          )}
          {enrollToken && (
            <>
              <p className="mb-1 font-medium">Token de enrolamiento (se muestra una sola vez):</p>
              <code className="block break-all rounded bg-slate-900 px-2 py-1 text-xs text-slate-200">{enrollToken}</code>
              <p className="mt-3 mb-1 font-medium">Ejecuta esto en el nuevo servidor, dentro de la carpeta del Agente:</p>
              <code className="block break-all rounded bg-slate-900 px-2 py-1 text-xs text-slate-200">
                {server.os_type === 'linux' ? 'python3' : 'python'} enroll.py --core-url {coreUrl} --server-id {id} --token {enrollToken}
              </code>
              <p className="mt-2 text-xs text-amber-400">
                <a href="/docs/instalar-agente.html" target="_blank" rel="noopener" className="underline hover:text-amber-300">
                  Ver guía paso a paso
                </a>
                .
              </p>
            </>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="mt-2"
            onClick={() => {
              setShowManualToken(false)
              setEnrollToken(null)
            }}
          >
            Cerrar
          </Button>
        </div>
      )}
      </>
      )}

      {!metrics?.metrics_updated_at && (
        <div className="mb-6 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 text-sm text-slate-400">
          Todavía no se recibieron métricas de este servidor. Verifica que el Agente CITI esté instalado y conectado.
        </div>
      )}

      {metrics?.metrics_updated_at && (
        <Card className="mb-6">
          <CardContent className="grid grid-cols-2 gap-4 py-4 sm:grid-cols-3 lg:grid-cols-5">
            <InfoField label="Kernel / SO" value={metrics.kernel_version ?? server.os_version ?? '—'} />
            <InfoField label="Uptime" value={formatUptime(metrics.uptime_seconds)} />
            <InfoField label="Modelo de CPU" value={metrics.cpu_model ?? '—'} />
            <InfoField
              label="Carga (1 min)"
              value={metrics.load_average_1m != null ? metrics.load_average_1m.toFixed(2) : 'N/D (Windows)'}
            />
            <InfoField label="Versión del agente" value={metrics.agent_version ?? '—'} />
          </CardContent>
        </Card>
      )}

      <div className="mb-6 flex gap-1 overflow-x-auto border-b border-slate-800">
        {detailTabs.map((t) => {
          const Icon = t.icon
          return (
            <button
              key={t.key}
              onClick={() => setDetailTab(t.key)}
              className={cn(
                'flex shrink-0 items-center gap-1.5 px-4 py-2 text-sm transition-colors',
                detailTab === t.key ? 'border-b-2 border-amber-500 text-slate-100' : 'text-slate-400 hover:text-slate-200',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
            </button>
          )
        })}
      </div>

      {detailTab === 'resumen' && (
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <GaugeCard icon={Cpu} label="CPU" percent={metrics?.cpu_percent} color={pctColorHex(metrics?.cpu_percent, cpuThresholds.warn, cpuThresholds.crit)} />
        <GaugeCard
          icon={MemoryStick}
          label="Memoria RAM"
          percent={metrics?.ram_percent}
          color={pctColorHex(metrics?.ram_percent, ramThresholds.warn, ramThresholds.crit)}
        >
          {metrics?.ram_used_mb != null && metrics?.ram_total_mb != null && (
            <p className="mt-0.5 text-xs text-slate-500">
              {(metrics.ram_used_mb / 1024).toFixed(1)} GB / {(metrics.ram_total_mb / 1024).toFixed(1)} GB
            </p>
          )}
        </GaugeCard>
        <GaugeCard
          icon={HardDrive}
          label="Disco (peor)"
          percent={worstDiskPercent}
          color={pctColorHex(worstDiskPercent, worstDiskThresholds.warn, worstDiskThresholds.crit)}
        >
          <p className="mt-0.5 text-xs text-slate-500">
            {metrics?.disks?.length ?? 0} {metrics?.disks?.length === 1 ? 'disco' : 'discos'} — detalle abajo
          </p>
        </GaugeCard>
      </div>
      )}

      {detailTab === 'red' && (
      <div className="mb-6 grid grid-cols-2 gap-4">
        <StatCard icon={Network} label="Red enviada" value={formatBytes(metrics?.net_bytes_sent)}>
          <p className="mt-1 text-xs text-slate-500">Recibido: {formatBytes(metrics?.net_bytes_recv)}</p>
        </StatCard>
        <StatCard icon={Network} label="Velocidad de red" value={formatMbps(metrics?.net_recv_rate_mbps)}>
          <p className="mt-1 text-xs text-slate-500">Subida: {formatMbps(metrics?.net_sent_rate_mbps)}</p>
        </StatCard>
      </div>
      )}

      {detailTab === 'disco' && (
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard icon={Gauge} label="I/O de disco (total)" value={formatMBps(metrics?.disk_read_mbps)}>
          <p className="mt-1 text-xs text-slate-500">Escritura: {formatMBps(metrics?.disk_write_mbps)}</p>
        </StatCard>
      </div>
      )}

      {detailTab === 'disco' && metrics?.disks && metrics.disks.length > 0 && (
        <Card className="mb-6">
          <CardContent className="py-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-medium text-slate-200">Espacio en disco</h3>
              {diskForecast?.days_until_full != null && (
                <span
                  className={cn(
                    'text-xs',
                    diskForecast.days_until_full <= 7
                      ? 'text-red-400'
                      : diskForecast.days_until_full <= 30
                        ? 'text-amber-400'
                        : 'text-slate-500',
                  )}
                >
                  A este ritmo, el disco con más uso se llenará en ~{Math.round(diskForecast.days_until_full)}{' '}
                  {Math.round(diskForecast.days_until_full) === 1 ? 'día' : 'días'} (últimos {diskForecast.sample_days} días)
                </span>
              )}
            </div>
            <div className="flex flex-col gap-3">
              {metrics.disks.map((disk) => {
                const diskThresholds = thresholdsForMetric(
                  alertRules, id, 'disk_percent_used', disk.mount, DISK_WARN, DISK_CRIT,
                )
                return (
                  <div key={disk.mount}>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span className="text-slate-300">{disk.mount}</span>
                      <span className={pctColor(disk.percent_used, diskThresholds.warn, diskThresholds.crit)}>
                        {disk.percent_used.toFixed(1)}% usado · {disk.free_gb.toFixed(1)} GB libres de {disk.total_gb.toFixed(1)} GB
                      </span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className={cn('h-full rounded-full', barColor(disk.percent_used, diskThresholds.warn, diskThresholds.crit))}
                        style={{ width: `${Math.min(disk.percent_used, 100)}%` }}
                      />
                    </div>
                    {disk.inode_used_percent != null && (
                      <p className={cn('mt-1 text-xs', pctColor(disk.inode_used_percent, DISK_WARN, DISK_CRIT))}>
                        Inodos: {disk.inode_used_percent.toFixed(1)}% usado
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {detailTab === 'disco' && metrics?.disk_io && metrics.disk_io.length > 0 && (
        <Card className="mb-6">
          <CardContent className="py-5">
            <h3 className="mb-3 flex items-center gap-1.5 text-sm font-medium text-slate-200">
              <Gauge className="h-4 w-4" /> E/S de disco físico
            </h3>
            <p className="mb-3 text-xs text-slate-500">
              Por dispositivo físico, no por unidad — un disco puede tener varias unidades (C:\, D:\) o formar parte de
              un RAID/LVM, así que esto no siempre corresponde 1 a 1 con la tabla de espacio de arriba.
            </p>
            <div className="overflow-hidden rounded-lg border border-slate-800">
              <table className="w-full text-xs">
                <thead className="bg-slate-900/60 text-left uppercase text-slate-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">Disco</th>
                    <th className="px-3 py-2 font-medium">Lectura</th>
                    <th className="px-3 py-2 font-medium">Escritura</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {metrics.disk_io.map((disk) => (
                    <tr key={disk.device}>
                      <td className="px-3 py-1.5 text-slate-200">{disk.device}</td>
                      <td className="px-3 py-1.5 text-slate-300">{formatMBps(disk.read_mbps)}</td>
                      <td className="px-3 py-1.5 text-slate-300">{formatMBps(disk.write_mbps)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {detailTab === 'disco' && metrics?.disk_health_available != null && (
        <Card className="mb-6">
          <CardContent className="py-5">
            <h3 className="mb-3 flex items-center gap-1.5 text-sm font-medium text-slate-200">
              <HardDrive className="h-4 w-4" /> Salud física de disco (SMART)
            </h3>
            {!metrics.disk_health_available && (
              <p className="text-sm text-slate-500">
                <code className="rounded bg-slate-900 px-1.5 py-0.5 text-xs">smartctl</code> no está instalado en este
                servidor — no se puede leer la salud física de los discos.
              </p>
            )}
            {metrics.disk_health_available && (!metrics.disk_health || metrics.disk_health.length === 0) && (
              <p className="text-sm text-slate-500">No se detectaron discos con datos SMART disponibles.</p>
            )}
            {metrics.disk_health_available && metrics.disk_health && metrics.disk_health.length > 0 && (
              <div className="overflow-hidden rounded-lg border border-slate-800">
                <table className="w-full text-xs">
                  <thead className="bg-slate-900/60 text-left uppercase text-slate-500">
                    <tr>
                      <th className="px-3 py-2 font-medium">Disco</th>
                      <th className="px-3 py-2 font-medium">Tipo</th>
                      <th className="px-3 py-2 font-medium">Horas encendido</th>
                      <th className="px-3 py-2 font-medium">Test SMART</th>
                      <th className="px-3 py-2 font-medium">Errores</th>
                      <th className="px-3 py-2 font-medium">Desgaste</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {metrics.disk_health.map((disk) => (
                      <tr key={disk.device}>
                        <td className="px-3 py-1.5 text-slate-200">{disk.device}</td>
                        <td className="px-3 py-1.5 text-slate-400 uppercase">{disk.type.replace('_', '/')}</td>
                        <td className="px-3 py-1.5 text-slate-300">
                          {disk.power_on_hours != null ? Math.round(disk.power_on_hours).toLocaleString('es-PE') : '—'}
                        </td>
                        <td className="px-3 py-1.5">
                          {disk.smart_passed == null ? (
                            <span className="text-slate-500">—</span>
                          ) : disk.smart_passed ? (
                            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                          ) : (
                            <XCircle className="h-3.5 w-3.5 text-red-400" />
                          )}
                        </td>
                        <td className={cn('px-3 py-1.5', disk.error_count ? 'text-amber-400' : 'text-slate-400')}>
                          {disk.error_count ?? '—'}
                        </td>
                        <td className={cn('px-3 py-1.5', wearoutColor(disk.wearout_percent))}>
                          {disk.wearout_percent != null ? `${disk.wearout_percent.toFixed(0)}%` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {detailTab === 'actividad' && uptime && (
        <Card className="mb-6">
          <CardContent className="py-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="flex items-center gap-1.5 text-sm font-medium text-slate-200">
                <History className="h-4 w-4" /> Disponibilidad (últimos {uptime.window_days} días)
              </h3>
              <span className={cn('text-lg font-semibold', uptimeColor(uptime.uptime_percent))}>
                {uptime.uptime_percent.toFixed(2)}%
              </span>
            </div>
            {uptime.outages.length === 0 ? (
              <p className="text-sm text-slate-500">Sin interrupciones de conectividad registradas en este periodo.</p>
            ) : (
              <div className="flex flex-col divide-y divide-slate-800">
                {uptime.outages.slice(0, 5).map((outage, i) => (
                  <div key={i} className="flex items-center justify-between gap-4 py-2 text-sm">
                    <span className={outage.ended_at ? 'text-slate-300' : 'text-red-400'}>
                      {outage.ended_at ? `Desconectado ${timeAgo(outage.started_at)}` : 'Desconectado ahora mismo'}
                    </span>
                    <span className="text-slate-500">
                      {outage.ended_at
                        ? formatOutageDuration(outage.duration_seconds)
                        : `desde hace ${formatOutageDuration(outage.duration_seconds)}`}
                    </span>
                  </div>
                ))}
                {uptime.outages.length > 5 && (
                  <p className="pt-2 text-xs text-slate-500">+{uptime.outages.length - 5} interrupciones más</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {detailTab === 'resumen' && history && history.length > 1 && (
        <Card className="mb-6">
          <CardContent className="py-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-medium text-slate-200">Tendencia</h3>
              <div className="flex gap-1 rounded-lg border border-slate-800 p-0.5">
                {HISTORY_RANGES.map((range) => (
                  <button
                    key={range.hours}
                    onClick={() => setHistoryHours(range.hours)}
                    className={cn(
                      'rounded-md px-2.5 py-1 text-xs transition-colors',
                      historyHours === range.hours ? 'bg-amber-500/15 text-amber-300' : 'text-slate-400 hover:text-slate-200',
                    )}
                  >
                    {range.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history} margin={{ top: 5, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis
                    dataKey="recorded_at"
                    tickFormatter={(v: string) =>
                      historyHours > 48
                        ? new Date(v).toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit' })
                        : new Date(v).toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })
                    }
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    stroke="#334155"
                    minTickGap={40}
                  />
                  <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 11 }} stroke="#334155" width={36} />
                  <Tooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }}
                    labelFormatter={(v) => new Date(v as string).toLocaleString('es-PE')}
                    formatter={(value, name) => [`${typeof value === 'number' ? value.toFixed(1) : value}%`, name]}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="cpu_percent" name="CPU" stroke="#38bdf8" dot={false} strokeWidth={1.75} connectNulls />
                  <Line type="monotone" dataKey="ram_percent" name="RAM" stroke="#a78bfa" dot={false} strokeWidth={1.75} connectNulls />
                  <Line
                    type="monotone"
                    dataKey="disk_percent_used"
                    name="Disco (peor)"
                    stroke="#fb923c"
                    dot={false}
                    strokeWidth={1.75}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {detailTab === 'red' && networkPath?.current && (
        <Card className="mb-6">
          <CardContent className="py-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="flex items-center gap-1.5 text-sm font-medium text-slate-200">
                <Network className="h-4 w-4" /> Diagnóstico de red (ruta hacia Core)
              </h3>
              <div className="flex items-center gap-3">
                {networkPath.current.quality_score != null && (
                  <div className="relative flex shrink-0 items-center justify-center" style={{ width: 40, height: 40 }}>
                    <CircularGauge
                      percent={networkPath.current.quality_score}
                      size={40}
                      strokeWidth={5}
                      colorClassName={
                        networkPath.current.quality_score >= 85
                          ? 'text-emerald-400'
                          : networkPath.current.quality_score >= 50
                            ? 'text-amber-400'
                            : 'text-red-400'
                      }
                    />
                    <span className="absolute text-[11px] font-semibold text-slate-100">
                      {networkPath.current.quality_score}
                    </span>
                  </div>
                )}
                <StatusChip tone={networkPath.current.reachable ? 'ok' : 'critical'}>
                  {networkPath.current.reachable ? 'RUTA COMPLETA' : 'DESTINO NO RESPONDE'}
                </StatusChip>
              </div>
            </div>

            <div className="mb-4 overflow-hidden rounded-lg border border-slate-800">
              <table className="w-full text-xs">
                <thead className="bg-slate-900/60 text-left uppercase text-slate-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">Salto</th>
                    <th className="px-3 py-2 font-medium">Dirección</th>
                    <th className="px-3 py-2 font-medium">Latencia</th>
                    <th className="px-3 py-2 font-medium">Pérdida</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {networkPath.current.hops.map((hop) => (
                    <tr key={hop.hop_number}>
                      <td className="px-3 py-1.5 text-slate-400">{hop.hop_number}</td>
                      <td className="px-3 py-1.5 text-slate-200">{hop.address ?? 'Sin respuesta'}</td>
                      <td className="px-3 py-1.5 text-slate-300">
                        {hop.avg_latency_ms != null ? `${hop.avg_latency_ms.toFixed(1)} ms` : '—'}
                      </td>
                      <td className={cn('px-3 py-1.5', (hop.packet_loss_percent ?? 0) > 0 ? 'text-amber-400' : 'text-slate-500')}>
                        {hop.packet_loss_percent != null ? `${hop.packet_loss_percent.toFixed(0)}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {networkChartData.length > 1 && (
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={networkChartData} margin={{ top: 5, right: 12, bottom: 0, left: -12 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis
                      dataKey="recorded_at"
                      tickFormatter={(v: string) => new Date(v).toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })}
                      tick={{ fill: '#64748b', fontSize: 11 }}
                      stroke="#334155"
                      minTickGap={40}
                    />
                    <YAxis tick={{ fill: '#64748b', fontSize: 11 }} stroke="#334155" width={36} />
                    <Tooltip
                      contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }}
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      labelFormatter={((v: string) => new Date(v).toLocaleString('es-PE')) as any}
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      formatter={((value: number, name: string) => [value != null ? `${value.toFixed(1)} ms` : '—', name]) as any}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {networkHopNumbers.map((hopNumber, i) => (
                      <Line
                        key={hopNumber}
                        type="monotone"
                        dataKey={`hop_${hopNumber}`}
                        name={`Salto ${hopNumber}`}
                        stroke={HOP_LINE_COLORS[i % HOP_LINE_COLORS.length]}
                        dot={false}
                        strokeWidth={1.5}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            <p className="mt-3 text-xs text-slate-500">
              Algunos saltos intermedios pueden mostrar "pérdida" sin que sea un problema real: muchos routers
              despriorizan intencionalmente sus respuestas ICMP. El último salto (destino) es el que refleja la
              conectividad real hacia Core.
            </p>
          </CardContent>
        </Card>
      )}

      {detailTab === 'servicios' && (
        <Card className="mb-6">
          <CardContent className="py-5">
            <h3 className="mb-3 text-sm font-medium text-slate-200">Servicios</h3>
            {(!services || services.length === 0) && (
              <p className="text-sm text-slate-500">
                Este servidor no tiene servicios registrados todavía. Se agregan desde la pantalla del Sistema
                correspondiente (Servicios → + Nuevo servicio), asignándole este servidor.
              </p>
            )}
            {services && services.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">Servicio</th>
                    <th className="px-4 py-2 font-medium">Puerto</th>
                    <th className="px-4 py-2 font-medium">Conexiones</th>
                    <th className="px-4 py-2 font-medium">Estado</th>
                    <th className="px-4 py-2 font-medium">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {services.map((service) => {
                    const connectionCount = service.port != null ? portConnectionByPort.get(service.port) : undefined
                    return (
                      <tr key={service.id}>
                        <td className="px-4 py-2 text-slate-100">
                          {service.name}
                          {service.control_identifier && (
                            <div className="text-xs text-slate-500">{service.control_identifier}</div>
                          )}
                        </td>
                        <td className="px-4 py-2 text-slate-400">{service.port ?? '—'}</td>
                        <td className="px-4 py-2 text-slate-400">
                          {service.port == null ? (
                            '—'
                          ) : connectionCount == null ? (
                            <span className="text-amber-400" title="El agente no reporta este puerto como abierto ahora mismo">
                              sin escuchar
                            </span>
                          ) : (
                            connectionCount
                          )}
                        </td>
                        <td className="px-4 py-2">
                          <StatusChip tone={serviceStatusTone[service.status]}>{service.status.toUpperCase()}</StatusChip>
                        </td>
                        <td className="px-4 py-2">
                          {service.type === 'database' ? (
                            <span
                              className="text-xs text-slate-500"
                              title="Instancia de Postgres compartida por varios sistemas: no se controla desde aquí"
                            >
                              No controlable (instancia compartida)
                            </span>
                          ) : (
                            <ServiceActions serviceId={service.id} />
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            )}
          </CardContent>
        </Card>
      )}

      {detailTab === 'servicios' && metrics?.port_connections && metrics.port_connections.length > 0 && (
        <Card className="mb-6">
          <CardContent className="py-5">
            <h3 className="mb-1 text-sm font-medium text-slate-200">Puertos en escucha</h3>
            <p className="mb-3 text-xs text-slate-500">
              Todo lo que el agente detecta escuchando en este servidor ahora mismo, tenga o no un Servicio
              registrado arriba — útil para confirmar que algo realmente está recibiendo tráfico.
            </p>
            <div className="overflow-hidden rounded-lg border border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">Puerto</th>
                    <th className="px-4 py-2 font-medium">Conexiones activas</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {metrics.port_connections.map((pc) => (
                    <tr key={pc.port}>
                      <td className="px-4 py-2 text-slate-200">{pc.port}</td>
                      <td className={cn('px-4 py-2', pc.connection_count > 0 ? 'text-slate-100' : 'text-slate-500')}>
                        {pc.connection_count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {detailTab === 'procesos' && (metrics?.top_cpu_processes?.length || metrics?.top_ram_processes?.length) && (
        <Card className="mb-6">
          <CardContent className="py-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="flex items-center gap-1.5 text-sm font-medium text-slate-200">
                <Activity className="h-4 w-4" /> Procesos
              </h3>
              {metrics?.processes_updated_at && (
                <span className="text-xs text-slate-500">Actualizado {timeAgo(metrics.processes_updated_at)}</span>
              )}
            </div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div>
                <p className="mb-1.5 text-xs uppercase text-slate-500">Mayor consumo de CPU</p>
                <table className="w-full text-xs">
                  <tbody className="divide-y divide-slate-800">
                    {metrics?.top_cpu_processes?.map((p) => (
                      <tr key={p.pid}>
                        <td className="py-1.5 pr-2 text-slate-300">{p.name ?? `PID ${p.pid}`}</td>
                        <td className="py-1.5 pr-2 text-right text-slate-500">{p.ram_mb} MB</td>
                        <td className="py-1.5 text-right font-medium text-slate-100">{p.cpu_percent.toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <p className="mb-1.5 text-xs uppercase text-slate-500">Mayor consumo de RAM</p>
                <table className="w-full text-xs">
                  <tbody className="divide-y divide-slate-800">
                    {metrics?.top_ram_processes?.map((p) => (
                      <tr key={p.pid}>
                        <td className="py-1.5 pr-2 text-slate-300">{p.name ?? `PID ${p.pid}`}</td>
                        <td className="py-1.5 pr-2 text-right text-slate-500">{p.cpu_percent.toFixed(1)}%</td>
                        <td className="py-1.5 text-right font-medium text-slate-100">{p.ram_mb} MB</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {detailTab === 'actividad' && (
      <Card className="mb-6">
        <CardContent className="py-5">
          <h3 className="mb-1 flex items-center gap-1.5 text-sm font-medium text-slate-200">
            <AlertTriangle className="h-4 w-4" /> Eventos críticos del sistema
          </h3>
          <p className="mb-3 text-xs text-slate-500">
            Historial del sistema operativo para revisión — no todos requieren acción inmediata. A diferencia de las
            alertas, estos no generan notificaciones ni correos automáticos.
          </p>
          {events && events.length === 0 && (
            <p className="text-sm text-slate-500">Sin eventos críticos o de error registrados.</p>
          )}
          {events && events.length > 0 && (
            <div className="flex flex-col gap-2">
              {events.map((event) => (
                <div key={event.id} className="rounded-lg border border-slate-800 px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <StatusChip tone={eventLevelTone(event.level)}>{eventLevelLabel(event.level).toUpperCase()}</StatusChip>
                    <span>{event.log_name}</span>
                    {event.provider && <span>{event.provider}</span>}
                    {event.event_id != null && <span>ID {event.event_id}</span>}
                    <span className="ml-auto">{timeAgo(event.occurred_at)}</span>
                  </div>
                  {event.message && <p className="mt-1 whitespace-pre-line text-sm text-slate-300">{event.message}</p>}
                </div>
              ))}
            </div>
          )}
          {events && events.length === eventsLimit && (
            <button className="mt-3 text-xs text-amber-400 hover:text-amber-300" onClick={() => setEventsLimit((n) => n + 15)}>
              Ver más
            </button>
          )}
        </CardContent>
      </Card>
      )}

      {detailTab === 'actividad' && (
      <Card className="mb-6">
        <CardContent className="py-5">
          <h3 className="mb-3 flex items-center gap-1.5 text-sm font-medium text-slate-200">
            <NotebookPen className="h-4 w-4" /> Bitácora
          </h3>
          <form onSubmit={handleCreateNote} className="mb-4 flex flex-col gap-2">
            <Textarea
              placeholder="Anota lo que hiciste, observaste o dejaste pendiente en este servidor…"
              value={noteBody}
              onChange={(e) => setNoteBody(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <Button type="submit" size="sm" disabled={createNote.isPending || !noteBody.trim()}>
                {createNote.isPending ? 'Guardando…' : 'Agregar nota'}
              </Button>
              {createNote.isError && <ErrorMessage className="text-xs">No se pudo guardar la nota.</ErrorMessage>}
            </div>
          </form>
          {notes && notes.length === 0 && <p className="text-sm text-slate-500">Sin notas registradas todavía.</p>}
          {notes && notes.length > 0 && (
            <div className="flex flex-col gap-3">
              {notes.map((note) => (
                <div key={note.id} className="border-l-2 border-slate-700 pl-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="font-medium text-slate-300">{note.author_name ?? 'Usuario eliminado'}</span>
                    <span>{timeAgo(note.created_at)}</span>
                  </div>
                  <p className="mt-0.5 whitespace-pre-line text-sm text-slate-300">{note.body}</p>
                </div>
              ))}
            </div>
          )}
          {notes && notes.length === notesLimit && (
            <button className="mt-3 text-xs text-amber-400 hover:text-amber-300" onClick={() => setNotesLimit((n) => n + 15)}>
              Ver más
            </button>
          )}
        </CardContent>
      </Card>
      )}

      {detailTab === 'actividad' && (
      <Card>
        <CardContent className="py-5">
          <h3 className="mb-3 text-sm font-medium text-slate-200">Actividad reciente</h3>
          {activity && activity.length === 0 && (
            <p className="text-sm text-slate-500">Sin actividad ni fallos registrados para este servidor.</p>
          )}
          {activity && activity.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-slate-800">
              <table className="w-full text-xs">
                <thead className="bg-slate-900/60 text-left uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">Fecha</th>
                    <th className="px-4 py-2 font-medium">Evento</th>
                    <th className="px-4 py-2 font-medium">Estado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {activity.map((item, i) => (
                    <tr key={i}>
                      <td className="whitespace-nowrap px-4 py-2 text-slate-500">{timeAgo(item.occurred_at)}</td>
                      <td className="px-4 py-2">
                        <p className="text-slate-200">{item.title}</p>
                        {item.detail && <p className="mt-0.5 max-w-lg truncate text-slate-500">{item.detail}</p>}
                      </td>
                      <td className="px-4 py-2">
                        <StatusChip tone={activityTone(item)}>{activityStatusLabel(item).toUpperCase()}</StatusChip>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {activity && activity.length === activityLimit && (
            <button
              className="mt-3 text-xs text-amber-400 hover:text-amber-300"
              onClick={() => setActivityLimit((n) => n + 12)}
            >
              Ver más
            </button>
          )}
        </CardContent>
      </Card>
      )}

      <Dialog open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Eliminar servidor</DialogTitle>
            <DialogDescription>
              ¿Eliminar el servidor "{server.hostname}"? Se perderá todo su historial de métricas, eventos y bitácora.
              Esta acción no se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDeleteOpen(false)}>
              Cancelar
            </Button>
            <Button variant="destructive" disabled={deleteServer.isPending} onClick={() => deleteServer.mutate()}>
              {deleteServer.isPending ? 'Eliminando…' : 'Eliminar servidor'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
