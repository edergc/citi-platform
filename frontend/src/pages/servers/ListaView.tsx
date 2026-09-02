import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Cpu, HardDrive, MemoryStick, Pencil, Search, Wrench } from 'lucide-react'
import { Line, LineChart, ResponsiveContainer } from 'recharts'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import {
  SERVER_USAGE_TAGS,
  type Server,
  type ServerHealth,
  type ServerSparkline,
  type Site,
} from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TableSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { Pagination } from '@/components/ui/pagination'
import { ServerFormDialog } from '@/components/ServerFormDialog'
import { HealthBadge } from '@/components/HealthBadge'
import { HexagonStat } from '@/components/ui/hexagon-stat'
import { StatusChip } from '@/components/ui/status-chip'
import { cn } from '@/lib/utils'
import { ALL_HEALTH, ALL_SITES, ALL_USAGE, HEALTH_COLORS, healthFilterLabel, statusLabel, statusTone } from './shared'

const PAGE_SIZE = 25

function TrendSparkline({ points }: { points: { recorded_at: string; cpu_percent: number | null; ram_percent: number | null }[] }) {
  if (points.length === 0) {
    return <span className="text-xs text-slate-600">—</span>
  }
  // The most recent sample doubles as "current usage" — up to ~5 min old (the
  // sampling interval behind /servers/sparklines), not a live 15s reading, but a real
  // number a técnico can act on, unlike the site-level average this replaced.
  const latest = points[points.length - 1]
  return (
    <div className="flex items-center gap-2">
      <div className="text-xs text-slate-400">
        <span className="text-sky-400">{latest.cpu_percent != null ? `${Math.round(latest.cpu_percent)}%` : '—'}</span>
        {' · '}
        <span className="text-purple-400">{latest.ram_percent != null ? `${Math.round(latest.ram_percent)}%` : '—'}</span>
      </div>
      {points.length >= 2 && (
        <div className="h-7 w-16 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
              <Line type="monotone" dataKey="cpu_percent" stroke="#38bdf8" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
              <Line type="monotone" dataKey="ram_percent" stroke="#c084fc" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export function ListaView() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const { data: servers, isLoading, isError } = useQuery({
    queryKey: ['servers'],
    queryFn: async () => (await api.get<Server[]>('/servers')).data,
  })

  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
  })
  const siteName = new Map((sites ?? []).map((s) => [s.id, s.name]))
  const siteCode = new Map((sites ?? []).map((s) => [s.id, s.code]))

  const { data: sparklines } = useQuery({
    queryKey: ['servers', 'sparklines'],
    queryFn: async () => (await api.get<ServerSparkline[]>('/servers/sparklines', { params: { hours: 6 } })).data,
    refetchInterval: 60000,
  })
  const sparklineByServer = new Map((sparklines ?? []).map((s) => [s.server_id, s.points]))

  // Derived straight from the URL (not local state) so it reacts when the query string
  // changes without a remount — e.g. clicking a sede tile in Resumen while already on
  // this same /servers route, which only pushes a new search string, not a navigation.
  const siteFilter = searchParams.get('site') ?? ALL_SITES
  const [healthFilter, setHealthFilter] = useState<ServerHealth | typeof ALL_HEALTH>(ALL_HEALTH)
  const [usageFilter, setUsageFilter] = useState(ALL_USAGE)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  function handleSiteFilterChange(value: string) {
    // Keep the URL's ?site= in sync so the filtered view stays linkable/bookmarkable —
    // this is also what the sede tiles and Admin → Sedes button set.
    const next = new URLSearchParams(searchParams)
    if (value === ALL_SITES) {
      next.delete('site')
    } else {
      next.set('site', value)
    }
    setSearchParams(next, { replace: true })
    setPage(1)
  }

  function toggleHealthFilter(health: ServerHealth) {
    setHealthFilter((current) => (current === health ? ALL_HEALTH : health))
    setPage(1)
  }

  const filteredServers = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (servers ?? []).filter((server) => {
      if (siteFilter !== ALL_SITES && server.site_id !== siteFilter) return false
      if (healthFilter !== ALL_HEALTH && server.health !== healthFilter) return false
      if (usageFilter !== ALL_USAGE && !server.usage_tags.includes(usageFilter)) return false
      if (
        term &&
        !server.hostname.toLowerCase().includes(term) &&
        !(server.ip_address ?? '').toLowerCase().includes(term)
      ) {
        return false
      }
      return true
    })
  }, [servers, siteFilter, healthFilter, usageFilter, search])

  const totalPages = Math.max(1, Math.ceil(filteredServers.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageServers = filteredServers.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  // Respects the sede filter (so the donut matches what the table below is scoped to)
  // but not the health/usage/search filters — otherwise selecting a slice would shrink
  // its own denominator.
  const healthCounts = useMemo(() => {
    const counts: Record<ServerHealth, number> = { ok: 0, warning: 0, critical: 0 }
    for (const server of servers ?? []) {
      if (siteFilter !== ALL_SITES && server.site_id !== siteFilter) continue
      counts[server.health]++
    }
    return counts
  }, [servers, siteFilter])

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {servers && servers.length > 0 && (
          <div className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
            <HexagonStat
              size={64}
              segments={[
                { value: healthCounts.critical, color: HEALTH_COLORS.critical, label: healthFilterLabel.critical },
                { value: healthCounts.warning, color: HEALTH_COLORS.warning, label: healthFilterLabel.warning },
                { value: healthCounts.ok, color: HEALTH_COLORS.ok, label: healthFilterLabel.ok },
              ]}
            />
            <div className="flex flex-wrap gap-1.5">
              {(['critical', 'warning', 'ok'] as ServerHealth[]).map((health) => {
                const count = healthCounts[health]
                const active = healthFilter === health
                return (
                  <button
                    key={health}
                    type="button"
                    onClick={() => toggleHealthFilter(health)}
                    className={cn(
                      'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                      active ? 'border-amber-500/50 bg-slate-800' : 'border-slate-800 hover:bg-slate-800/60',
                    )}
                  >
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: HEALTH_COLORS[health] }} />
                    <span className="text-slate-300">{healthFilterLabel[health]}</span>
                    <span className="font-medium text-slate-100">{count}</span>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input
            placeholder="Buscar por hostname o IP…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            className="pl-9"
          />
        </div>
        <Select value={siteFilter} onValueChange={handleSiteFilterChange}>
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
        <Select
          value={usageFilter}
          onValueChange={(v) => {
            setUsageFilter(v)
            setPage(1)
          }}
        >
          <SelectTrigger className="sm:w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_USAGE}>Todo uso</SelectItem>
            {SERVER_USAGE_TAGS.map((tag) => (
              <SelectItem key={tag} value={tag}>
                {tag}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && <TableSkeleton rows={8} cols={7} />}
      {isError && <ErrorMessage>No se pudo cargar la lista de servidores.</ErrorMessage>}
      {servers && servers.length === 0 && <p className="text-sm text-slate-400">Todavía no hay servidores registrados.</p>}
      {servers && servers.length > 0 && filteredServers.length === 0 && (
        <p className="text-sm text-slate-500">Ningún servidor coincide con los filtros aplicados.</p>
      )}

      {filteredServers.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Estado</th>
                <th className="px-4 py-2 font-medium">Servidor</th>
                <th className="px-4 py-2 font-medium">Sede</th>
                <th className="px-4 py-2 font-medium">Responsable</th>
                <th className="px-4 py-2 font-medium">Uso</th>
                <th className="px-4 py-2 font-medium">Recursos</th>
                <th className="px-4 py-2 font-medium">Conectividad</th>
                <th className="px-4 py-2 font-medium">
                  CPU / RAM actual
                  <span className="ml-1.5 inline-flex items-center gap-1 normal-case text-slate-600">
                    <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
                    CPU
                    <span className="h-1.5 w-1.5 rounded-full bg-purple-400" />
                    RAM (6h)
                  </span>
                </th>
                <th className="px-4 py-2 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {pageServers.map((server) => (
                <tr
                  key={server.id}
                  className="cursor-pointer hover:bg-slate-900/40"
                  onClick={() => navigate(`/servers/${server.id}`)}
                >
                  <td className="px-4 py-2">
                    <div className={cn(server.active_maintenance && 'opacity-60')}>
                      <HealthBadge health={server.health} reasons={server.health_reasons} />
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <p className="flex items-center gap-1.5 font-medium text-slate-100">
                      {server.hostname}
                      {server.active_maintenance && (
                        <span title={`En mantenimiento: ${server.active_maintenance.reason}`}>
                          <Wrench className="h-3.5 w-3.5 shrink-0 text-violet-400" />
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-slate-500">
                      {server.ip_address ?? '—'} · {server.os_type} {server.os_version}
                    </p>
                  </td>
                  <td className="px-4 py-2 text-slate-400" title={server.site_id ? siteName.get(server.site_id) : undefined}>
                    {server.site_id ? siteCode.get(server.site_id) ?? '—' : '—'}
                  </td>
                  <td className="px-4 py-2 text-slate-400">
                    {server.primary_responsible_user_name ?? <span className="text-amber-500/80">Sin asignar</span>}
                  </td>
                  <td className="px-4 py-2">
                    {server.usage_tags.length === 0 ? (
                      <span className="text-slate-500">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {server.usage_tags.slice(0, 2).map((tag) => (
                          <Badge key={tag} variant="default">
                            {tag}
                          </Badge>
                        ))}
                        {server.usage_tags.length > 2 && <Badge variant="default">+{server.usage_tags.length - 2}</Badge>}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2 text-slate-400">
                    <div className="flex items-center gap-2.5 text-xs">
                      <span className="flex items-center gap-1" title="vCPU declarados">
                        <Cpu className="h-3.5 w-3.5 text-slate-500" />
                        {server.cpu_cores ?? '—'}
                      </span>
                      <span className="flex items-center gap-1" title="RAM declarada">
                        <MemoryStick className="h-3.5 w-3.5 text-slate-500" />
                        {server.ram_mb ? `${Math.round(server.ram_mb / 1024)}G` : '—'}
                      </span>
                      <span className="flex items-center gap-1" title="Disco declarado">
                        <HardDrive className="h-3.5 w-3.5 text-slate-500" />
                        {server.disk_gb ? `${server.disk_gb}G` : '—'}
                      </span>
                    </div>
                  </td>
                  <td className={cn('px-4 py-2', server.active_maintenance && 'opacity-60')}>
                    <StatusChip tone={statusTone[server.status]}>{statusLabel[server.status].toUpperCase()}</StatusChip>
                  </td>
                  <td className="px-4 py-2">
                    <TrendSparkline points={sparklineByServer.get(server.id) ?? []} />
                  </td>
                  <td className="px-4 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                    {user?.is_superuser && (
                      <ServerFormDialog
                        server={server}
                        trigger={
                          <Button variant="ghost" size="sm" title="Editar" className="h-8 w-8 p-0">
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                        }
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {filteredServers.length > 0 && (
        <div className="mt-4 flex flex-col items-center gap-3 sm:flex-row sm:justify-between">
          <p className="text-xs text-slate-500">
            Mostrando {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filteredServers.length)} de{' '}
            {filteredServers.length} {filteredServers.length === 1 ? 'servidor' : 'servidores'}
          </p>
          <Pagination page={currentPage} totalPages={totalPages} onPageChange={setPage} />
        </div>
      )}
    </div>
  )
}
