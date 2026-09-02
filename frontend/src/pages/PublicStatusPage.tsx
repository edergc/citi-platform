import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  HelpCircle,
  Scale,
  Server,
  XCircle,
} from 'lucide-react'
import { api } from '@/lib/api'
import { InstitutionalHeaderBackdrop } from '@/components/InstitutionalHeaderBackdrop'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { StatusChip } from '@/components/ui/status-chip'
import { Pagination } from '@/components/ui/pagination'
import { cn } from '@/lib/utils'
import type { PublicServerStatus, PublicStatusValue, PublicSystemStatus } from '@/types'

const ALL_SITES = '__all__'
const SERVERS_PAGE_SIZE = 20

type StatusTab = 'services' | 'servers'

const statusMeta: Record<
  PublicStatusValue,
  { label: string; tone: 'ok' | 'warning' | 'critical' | 'neutral'; icon: typeof CheckCircle2 }
> = {
  operational: { label: 'Operativo', tone: 'ok', icon: CheckCircle2 },
  degraded: { label: 'Degradado', tone: 'warning', icon: AlertTriangle },
  down: { label: 'Caído', tone: 'critical', icon: XCircle },
  unknown: { label: 'Sin datos', tone: 'neutral', icon: HelpCircle },
}

const serverStatusMeta: Record<
  string,
  { label: string; tone: 'ok' | 'warning' | 'critical' | 'neutral'; icon: typeof CheckCircle2 }
> = {
  online: { label: 'En línea', tone: 'ok', icon: CheckCircle2 },
  offline: { label: 'Desconectado', tone: 'critical', icon: XCircle },
  degraded: { label: 'Degradado', tone: 'warning', icon: AlertTriangle },
  unknown: { label: 'Sin datos', tone: 'neutral', icon: HelpCircle },
}

interface SiteSummary {
  name: string
  total: number
  online: number
}

function siteHealthDotClass(summary: SiteSummary): string {
  if (summary.total === 0) return 'bg-slate-600'
  if (summary.online === summary.total) return 'bg-emerald-400'
  if (summary.online === 0) return 'bg-red-400'
  return 'bg-amber-400'
}

export function PublicStatusPage() {
  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['public-status'],
    queryFn: async () => (await api.get<PublicSystemStatus[]>('/public/status')).data,
    refetchInterval: 30_000,
  })

  const { data: servers, isLoading: serversLoading, isError: serversError } = useQuery({
    queryKey: ['public-servers'],
    queryFn: async () => (await api.get<PublicServerStatus[]>('/public/servers')).data,
    refetchInterval: 30_000,
  })

  const [activeTab, setActiveTab] = useState<StatusTab>('services')

  // null = show the sede overview grid; a name or ALL_SITES = drill into that view.
  const [siteFilter, setSiteFilter] = useState<string | null>(null)
  const [serversPage, setServersPage] = useState(1)

  const siteSummaries = useMemo<SiteSummary[]>(() => {
    const map = new Map<string, SiteSummary>()
    for (const s of servers ?? []) {
      const key = s.site_name ?? 'Sin sede'
      const entry = map.get(key) ?? { name: key, total: 0, online: 0 }
      entry.total += 1
      if (s.status === 'online') entry.online += 1
      map.set(key, entry)
    }
    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name))
  }, [servers])

  const filteredServers = useMemo(
    () => (servers ?? []).filter((s) => siteFilter === ALL_SITES || s.site_name === siteFilter),
    [servers, siteFilter],
  )

  const serversTotalPages = Math.max(1, Math.ceil(filteredServers.length / SERVERS_PAGE_SIZE))
  const serversCurrentPage = Math.min(serversPage, serversTotalPages)
  const pageServers = filteredServers.slice(
    (serversCurrentPage - 1) * SERVERS_PAGE_SIZE,
    serversCurrentPage * SERVERS_PAGE_SIZE,
  )

  function selectSite(site: string) {
    setSiteFilter(site)
    setServersPage(1)
  }

  const overall = data?.every((s) => s.status === 'operational')

  return (
    <div className="min-h-screen bg-slate-950">
      <header className="relative overflow-hidden border-b border-amber-500/20 px-6 py-5">
        <InstitutionalHeaderBackdrop />
        <div className="relative z-10 mx-auto flex max-w-3xl items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-amber-400/40 bg-red-950/50 backdrop-blur-sm">
            <Scale className="h-5 w-5 text-amber-400" />
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-widest text-amber-400/90">
              Poder Judicial del Perú — Corte Superior de Justicia de Lima
            </p>
            <p className="text-sm font-semibold text-white">Coordinación de Informática — CITI Platform</p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="mb-8 flex flex-col gap-1">
          <h1 className="text-2xl font-bold text-slate-100">Estado de los servicios</h1>
          <p className="text-sm text-slate-400">
            Consulta pública del estado de los sistemas institucionales. Actualizado automáticamente cada 30 segundos.
          </p>
        </div>

        {isLoading && (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
          </div>
        )}
        {isError && <ErrorMessage>No se pudo cargar el estado de los servicios.</ErrorMessage>}

        {data && (
          <>
            <Card className={overall ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-amber-500/30 bg-amber-500/5'}>
              <CardContent className="flex items-center gap-3 py-4">
                {overall ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                ) : (
                  <AlertTriangle className="h-5 w-5 text-amber-400" />
                )}
                <p className="text-sm font-medium text-slate-100">
                  {overall
                    ? 'Todos los sistemas operan con normalidad'
                    : 'Uno o más sistemas presentan incidencias'}
                </p>
              </CardContent>
            </Card>

            <div className="mt-6 flex gap-1 rounded-lg border border-slate-800 bg-slate-900/60 p-1">
              <button
                onClick={() => setActiveTab('services')}
                className={cn(
                  'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  activeTab === 'services'
                    ? 'bg-slate-800 text-slate-100'
                    : 'text-slate-400 hover:text-slate-200',
                )}
              >
                <Scale className="h-3.5 w-3.5" />
                Servicios
              </button>
              <button
                onClick={() => setActiveTab('servers')}
                className={cn(
                  'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  activeTab === 'servers'
                    ? 'bg-slate-800 text-slate-100'
                    : 'text-slate-400 hover:text-slate-200',
                )}
              >
                <Server className="h-3.5 w-3.5" />
                Servidores
              </button>
            </div>

            {activeTab === 'services' && (
              <div className="mt-4 flex flex-col gap-3">
                {data.map((system) => {
                  const meta = statusMeta[system.status]
                  const Icon = meta.icon
                  return (
                    <Card key={system.name}>
                      <CardHeader className="flex-row items-center justify-between gap-4 space-y-0">
                        <div>
                          <CardTitle className="text-base">{system.name}</CardTitle>
                          {system.category && <CardDescription>{system.category}</CardDescription>}
                        </div>
                        <StatusChip tone={meta.tone} className="flex items-center gap-1">
                          <Icon className="h-3.5 w-3.5" />
                          {meta.label.toUpperCase()}
                        </StatusChip>
                      </CardHeader>
                    </Card>
                  )
                })}
              </div>
            )}

            {activeTab === 'servers' && (
              <div className="mt-4">
                <p className="mb-3 text-xs text-slate-500">Elige una sede para ver el detalle de sus servidores.</p>

                {serversLoading && (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    <Skeleton className="h-16 w-full rounded-lg" />
                    <Skeleton className="h-16 w-full rounded-lg" />
                    <Skeleton className="h-16 w-full rounded-lg" />
                  </div>
                )}
                {serversError && <ErrorMessage>No se pudo cargar el estado de los servidores.</ErrorMessage>}

                {servers && siteFilter === null && (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    <button
                      onClick={() => selectSite(ALL_SITES)}
                      className="flex flex-col gap-1 rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-left shadow-lg shadow-black/20 transition-colors hover:border-amber-500/50"
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-slate-100">Todas las sedes</span>
                        <ChevronRight className="h-4 w-4 shrink-0 text-slate-500" />
                      </span>
                      <span className="text-xs text-slate-500">{servers.length} servidor{servers.length !== 1 ? 'es' : ''}</span>
                    </button>
                    {siteSummaries.map((summary) => (
                      <button
                        key={summary.name}
                        onClick={() => selectSite(summary.name)}
                        className="flex flex-col gap-1 rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-left shadow-lg shadow-black/20 transition-colors hover:border-amber-500/50"
                      >
                        <span className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-2 truncate text-sm font-medium text-slate-100">
                            <span className={cn('h-2 w-2 shrink-0 rounded-full', siteHealthDotClass(summary))} />
                            <span className="truncate">{summary.name}</span>
                          </span>
                          <ChevronRight className="h-4 w-4 shrink-0 text-slate-500" />
                        </span>
                        <span className="text-xs text-slate-500">
                          {summary.online} / {summary.total} en línea
                        </span>
                      </button>
                    ))}
                  </div>
                )}

                {servers && siteFilter !== null && (
                  <div>
                    <button
                      onClick={() => setSiteFilter(null)}
                      className="mb-3 inline-flex items-center gap-1 text-sm text-amber-400 hover:text-amber-300"
                    >
                      <ArrowLeft className="h-3.5 w-3.5" />
                      Ver todas las sedes
                    </button>

                    {filteredServers.length === 0 ? (
                      <p className="text-sm text-slate-500">No hay servidores registrados para esta sede.</p>
                    ) : (
                      <div className="overflow-hidden rounded-lg border border-slate-800">
                        <table className="w-full text-sm">
                          <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
                            <tr>
                              <th className="px-4 py-2 font-medium">Servidor</th>
                              {siteFilter === ALL_SITES && <th className="px-4 py-2 font-medium">Sede</th>}
                              <th className="px-4 py-2 font-medium">Estado</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800">
                            {pageServers.map((server) => {
                              const meta = serverStatusMeta[server.status] ?? serverStatusMeta.unknown
                              const Icon = meta.icon
                              return (
                                <tr key={server.hostname}>
                                  <td className="px-4 py-2.5 font-medium text-slate-100">{server.hostname}</td>
                                  {siteFilter === ALL_SITES && (
                                    <td className="px-4 py-2.5 text-slate-400">{server.site_name ?? '—'}</td>
                                  )}
                                  <td className="px-4 py-2.5">
                                    <StatusChip tone={meta.tone} className="flex w-fit items-center gap-1">
                                      <Icon className="h-3.5 w-3.5" />
                                      {meta.label.toUpperCase()}
                                    </StatusChip>
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                        {serversTotalPages > 1 && (
                          <div className="flex flex-col items-center gap-2 border-t border-slate-800 px-4 py-3 sm:flex-row sm:justify-between">
                            <p className="text-xs text-slate-500">
                              Mostrando {(serversCurrentPage - 1) * SERVERS_PAGE_SIZE + 1}–
                              {Math.min(serversCurrentPage * SERVERS_PAGE_SIZE, filteredServers.length)} de{' '}
                              {filteredServers.length}
                            </p>
                            <Pagination page={serversCurrentPage} totalPages={serversTotalPages} onPageChange={setServersPage} />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {dataUpdatedAt > 0 && (
              <p className="mt-6 text-center text-xs text-slate-500">
                Última actualización: {new Date(dataUpdatedAt).toLocaleTimeString('es-PE')}
              </p>
            )}
          </>
        )}

        <div className="mt-10 text-center">
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver al inicio de sesión
          </Link>
        </div>
      </main>
    </div>
  )
}
