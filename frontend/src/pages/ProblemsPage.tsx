import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '@/lib/api'
import type { AlertEvent, AlertSeverityLevel, ProblemKind, ProblemRow, Site } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TableSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { HexagonStat, HexagonLegend } from '@/components/ui/hexagon-stat'
import { StatusChip } from '@/components/ui/status-chip'
import { cn } from '@/lib/utils'
import { timeAgo } from '@/lib/format'

const ALL = '__all__'
const PAGE_SIZE = 40

const severityChipTone: Record<AlertSeverityLevel, 'info' | 'warning' | 'critical'> = {
  info: 'info',
  warning: 'warning',
  critical: 'critical',
}
const severityLabel: Record<AlertSeverityLevel, string> = {
  info: 'INFO',
  warning: 'WARN',
  critical: 'CRIT',
}
const severityColor: Record<AlertSeverityLevel, string> = {
  info: '#38bdf8',
  warning: '#fbbf24',
  critical: '#f87171',
}
const severityBorder: Record<AlertSeverityLevel, string> = {
  info: 'border-l-sky-400',
  warning: 'border-l-amber-400',
  critical: 'border-l-red-400',
}
const kindLabel: Record<ProblemKind, string> = {
  alert: 'Alerta',
  server_offline: 'Servidor caído',
  server_degraded: 'Servidor degradado',
  service_degraded: 'Servicio',
  backup_failed: 'Backup',
  deploy_failed: 'Despliegue',
  synthetic_failed: 'Chequeo sintético',
}

export function ProblemsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [kindFilter, setKindFilter] = useState<ProblemKind | typeof ALL>(ALL)
  const [severityFilter, setSeverityFilter] = useState<AlertSeverityLevel | typeof ALL>(ALL)
  const [siteFilter, setSiteFilter] = useState(ALL)
  const [limit, setLimit] = useState(PAGE_SIZE)

  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
  })

  const {
    data: problems,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['problems', { search, kindFilter, severityFilter, siteFilter, limit }],
    queryFn: async () =>
      (
        await api.get<ProblemRow[]>('/problems', {
          params: {
            limit,
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(kindFilter !== ALL ? { kind_filter: kindFilter } : {}),
            ...(severityFilter !== ALL ? { severity_filter: severityFilter } : {}),
            ...(siteFilter !== ALL ? { site_id_filter: siteFilter } : {}),
          },
        })
      ).data,
    refetchInterval: 30000,
  })

  const severityCounts: Record<AlertSeverityLevel, number> = { critical: 0, warning: 0, info: 0 }
  for (const p of problems ?? []) severityCounts[p.severity]++

  const acknowledgeEvent = useMutation({
    mutationFn: async (eventId: string) => api.post<AlertEvent>(`/alert-rules/events/${eventId}/acknowledge`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['problems'] })
      queryClient.invalidateQueries({ queryKey: ['alert-rules', 'events'] })
    },
  })

  function updateFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value)
      setLimit(PAGE_SIZE)
    }
  }

  function navigateToProblem(problem: ProblemRow) {
    if (problem.server_id) navigate(`/servers/${problem.server_id}`)
    else if (problem.system_id) navigate(`/systems/${problem.system_id}`)
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-slate-100">Problemas</h2>
        <p className="mt-1 text-sm text-slate-400">
          Todo lo que necesita atención ahora mismo en la flota — alertas abiertas, servidores caídos o degradados,
          servicios degradados, y el último backup o despliegue fallido de cada job/sistema.
        </p>
      </div>

      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-center gap-6 py-5">
          <HexagonStat
            segments={[
              { value: severityCounts.critical, color: severityColor.critical, label: severityLabel.critical },
              { value: severityCounts.warning, color: severityColor.warning, label: severityLabel.warning },
              { value: severityCounts.info, color: severityColor.info, label: severityLabel.info },
            ]}
          />
          <HexagonLegend
            segments={[
              { value: severityCounts.critical, color: severityColor.critical, label: 'Críticos' },
              { value: severityCounts.warning, color: severityColor.warning, label: 'Advertencias' },
              { value: severityCounts.info, color: severityColor.info, label: 'Informativos' },
            ]}
          />
          <div className="ml-auto text-right">
            <p className="text-3xl font-semibold text-slate-100">{problems?.length ?? 0}</p>
            <p className="text-xs uppercase tracking-wide text-slate-500">problemas totales</p>
          </div>
        </CardContent>
      </Card>

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input
            placeholder="Buscar por título, servidor o sistema…"
            value={search}
            onChange={(e) => updateFilter(setSearch)(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={kindFilter} onValueChange={updateFilter((v: string) => setKindFilter(v as typeof kindFilter))}>
          <SelectTrigger className="sm:w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todo tipo</SelectItem>
            {(Object.entries(kindLabel) as [ProblemKind, string][]).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={severityFilter}
          onValueChange={updateFilter((v: string) => setSeverityFilter(v as typeof severityFilter))}
        >
          <SelectTrigger className="sm:w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Toda severidad</SelectItem>
            <SelectItem value="critical">Crítico</SelectItem>
            <SelectItem value="warning">Advertencia</SelectItem>
            <SelectItem value="info">Informativo</SelectItem>
          </SelectContent>
        </Select>
        <Select value={siteFilter} onValueChange={updateFilter(setSiteFilter)}>
          <SelectTrigger className="sm:w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todas las sedes</SelectItem>
            {sites?.map((site) => (
              <SelectItem key={site.id} value={site.id}>
                {site.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && <TableSkeleton rows={8} cols={7} />}
      {isError && <ErrorMessage>No se pudo cargar el listado de problemas.</ErrorMessage>}
      {problems && problems.length === 0 && (
        <p className="text-sm text-slate-500">Ningún problema coincide con los filtros aplicados — o la flota está limpia.</p>
      )}

      {problems && problems.length > 0 && (
        <div className="flex flex-col gap-2">
          {problems.map((problem) => {
            const clickable = !!(problem.server_id || problem.system_id)
            return (
              <div
                key={problem.id}
                className={cn(
                  'flex flex-col gap-2 rounded-lg border border-l-4 border-slate-800 bg-slate-900/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between',
                  severityBorder[problem.severity],
                  problem.during_maintenance && 'opacity-60',
                )}
              >
                <div
                  className={cn('flex min-w-0 flex-1 flex-col gap-1', clickable && 'cursor-pointer')}
                  onClick={() => clickable && navigateToProblem(problem)}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusChip tone={severityChipTone[problem.severity]}>{severityLabel[problem.severity]}</StatusChip>
                    <Badge variant="default">{kindLabel[problem.kind]}</Badge>
                    {problem.during_maintenance && <Badge variant="maintenance">Mantenimiento</Badge>}
                    <span className="text-sm font-medium text-slate-100">{problem.title}</span>
                  </div>
                  <p className="text-xs text-slate-500">
                    {problem.detail && <>{problem.detail}</>}
                    {problem.hostname && (
                      <>
                        {problem.detail && ' · '}
                        <span className="text-slate-400">{problem.hostname}</span>
                      </>
                    )}
                    {problem.site_name && ` · ${problem.site_name}`}
                  </p>
                </div>

                <div className="flex shrink-0 flex-col items-start gap-1 sm:items-end" onClick={(e) => e.stopPropagation()}>
                  <span className="text-xs text-slate-500">{timeAgo(problem.occurred_at)}</span>
                  {problem.kind === 'alert' && problem.alert_event_id && (
                    problem.acknowledged_at ? (
                      <span className="text-xs text-slate-500">Reconocida {timeAgo(problem.acknowledged_at)}</span>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={acknowledgeEvent.isPending}
                        onClick={() => acknowledgeEvent.mutate(problem.alert_event_id!)}
                      >
                        Reconocer
                      </Button>
                    )
                  )}
                </div>
              </div>
            )
          })}

          {problems.length === limit && (
            <Button variant="outline" size="sm" className="self-center" onClick={() => setLimit((l) => l + PAGE_SIZE)}>
              Cargar más
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
