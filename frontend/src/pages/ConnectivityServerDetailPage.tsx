import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { api } from '@/lib/api'
import type { FleetConnectivityEvent, Server, ServerUptimeSummary } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton, TableSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { Pagination } from '@/components/ui/pagination'
import { GaugeCircle } from '@/components/ui/gauge-circle'
import { StatusChip } from '@/components/ui/status-chip'
import { cn } from '@/lib/utils'
import { timeAgo } from '@/lib/format'
import { extractMotivo } from '@/lib/connectivity'
import { statusLabel, statusTone } from './servers/shared'

const PAGE_SIZE = 15
const DAY_OPTIONS = [7, 30, 90, 180] as const
const ALL = '__all__'

const eventLabel: Record<FleetConnectivityEvent['event_type'], string> = {
  disconnected: 'Desconectado',
  reconnected: 'Reconectado',
}
const eventTone: Record<FleetConnectivityEvent['event_type'], 'critical' | 'ok'> = {
  disconnected: 'critical',
  reconnected: 'ok',
}

function uptimeColor(value: number): string {
  if (value >= 99) return '#34d399'
  if (value >= 95) return '#fbbf24'
  return '#f87171'
}

export function ConnectivityServerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [days, setDays] = useState<number>(30)
  const [eventTypeFilter, setEventTypeFilter] = useState<FleetConnectivityEvent['event_type'] | typeof ALL>(ALL)
  const [page, setPage] = useState(1)

  const { data: server, isLoading: serverLoading } = useQuery({
    queryKey: ['servers', id],
    queryFn: async () => (await api.get<Server>(`/servers/${id}`)).data,
    enabled: !!id,
  })

  const { data: uptime } = useQuery({
    queryKey: ['servers', id, 'uptime', days],
    queryFn: async () => (await api.get<ServerUptimeSummary>(`/servers/${id}/uptime`, { params: { days } })).data,
    enabled: !!id,
  })

  const {
    data: events,
    isLoading: eventsLoading,
    isError,
  } = useQuery({
    queryKey: ['servers', id, 'connectivity-events', days],
    queryFn: async () =>
      (
        await api.get<FleetConnectivityEvent[]>('/servers/connectivity-events', {
          params: { server_id_filter: id, days, limit: 300 },
        })
      ).data,
    enabled: !!id,
  })

  const filteredEvents = useMemo(() => {
    if (eventTypeFilter === ALL) return events ?? []
    return (events ?? []).filter((e) => e.event_type === eventTypeFilter)
  }, [events, eventTypeFilter])

  const totalPages = Math.max(1, Math.ceil(filteredEvents.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageEvents = filteredEvents.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  return (
    <div>
      <Link to="/connectivity" className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200">
        <ArrowLeft className="h-4 w-4" /> Volver a Conectividad
      </Link>

      {serverLoading && <Skeleton className="mb-6 h-16 w-full rounded-lg" />}
      {server && (
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold text-slate-100">{server.hostname}</h2>
              <StatusChip tone={statusTone[server.status]}>{statusLabel[server.status].toUpperCase()}</StatusChip>
            </div>
            <p className="mt-1 text-sm text-slate-400">
              {server.ip_address ?? '—'}
              {server.primary_responsible_user_name && ` · Responsable: ${server.primary_responsible_user_name}`}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate(`/servers/${server.id}`)}>
            Ver servidor completo →
          </Button>
        </div>
      )}

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <Select value={String(days)} onValueChange={(v) => { setDays(Number(v)); setPage(1) }}>
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
        <Select value={eventTypeFilter} onValueChange={(v) => { setEventTypeFilter(v as typeof eventTypeFilter); setPage(1) }}>
          <SelectTrigger className="sm:w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todo evento</SelectItem>
            <SelectItem value="disconnected">Desconexiones</SelectItem>
            <SelectItem value="reconnected">Reconexiones</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {uptime && (
        <Card className="mb-6">
          <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
            <div className="flex items-center gap-4">
              <GaugeCircle value={uptime.uptime_percent} color={uptimeColor(uptime.uptime_percent)} size={80} strokeWidth={8} />
              <p className="text-xs uppercase tracking-wide text-slate-500">Disponibilidad ({uptime.window_days} días)</p>
            </div>
            <div className="text-right">
              <p className="text-xs uppercase tracking-wide text-slate-500">Interrupciones</p>
              <p className="text-2xl font-semibold text-slate-200">{uptime.outages.length}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {eventsLoading && <TableSkeleton rows={6} cols={3} />}
      {isError && <ErrorMessage>No se pudo cargar el historial de conectividad de este servidor.</ErrorMessage>}
      {events && events.length === 0 && (
        <p className="text-sm text-slate-500">Sin eventos de conectividad registrados en este periodo.</p>
      )}
      {events && events.length > 0 && filteredEvents.length === 0 && (
        <p className="text-sm text-slate-500">Ningún evento coincide con el filtro aplicado.</p>
      )}

      {pageEvents.length > 0 && (
        <div className="flex flex-col gap-2">
          {pageEvents.map((event) => {
            const motivo = event.event_type === 'disconnected' ? extractMotivo(event.message) : null
            return (
              <div
                key={event.id}
                className={cn(
                  'flex flex-col gap-2 rounded-lg border border-l-4 border-slate-800 bg-slate-900/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between',
                  event.event_type === 'disconnected' ? 'border-l-red-400' : 'border-l-emerald-400',
                )}
              >
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <StatusChip tone={eventTone[event.event_type]}>{eventLabel[event.event_type].toUpperCase()}</StatusChip>
                  <p className="text-xs text-slate-500">
                    {event.event_type === 'disconnected'
                      ? motivo
                        ? `Motivo: ${motivo}`
                        : 'Motivo no registrado (evento anterior a esta función).'
                      : 'Reconexión correcta del Agente CITI.'}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-start gap-0.5 sm:items-end">
                  <span className="text-sm text-slate-300">{new Date(event.occurred_at).toLocaleString('es-PE')}</span>
                  <span className="text-xs text-slate-500">{timeAgo(event.occurred_at)}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {filteredEvents.length > 0 && (
        <div className="mt-4 flex flex-col items-center gap-3 sm:flex-row sm:justify-between">
          <p className="text-xs text-slate-500">
            Mostrando {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filteredEvents.length)} de{' '}
            {filteredEvents.length} {filteredEvents.length === 1 ? 'evento' : 'eventos'}
          </p>
          <Pagination page={currentPage} totalPages={totalPages} onPageChange={setPage} />
        </div>
      )}
    </div>
  )
}
