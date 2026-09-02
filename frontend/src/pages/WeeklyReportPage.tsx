import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArchiveX, CalendarRange, ServerOff, ShieldAlert } from 'lucide-react'
import { api } from '@/lib/api'
import type { Site, WeeklyReport } from '@/types'
import { useAuth } from '@/lib/auth'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { StatCardsSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { StatusChip } from '@/components/ui/status-chip'

const GLOBAL = '__global__'

const severityLabel: Record<string, string> = {
  critical: 'Crítico',
  warning: 'Advertencia',
  info: 'Informativo',
}

const severityTone: Record<string, 'critical' | 'warning' | 'info'> = {
  critical: 'critical',
  warning: 'warning',
  info: 'info',
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function ReportCard({ report }: { report: WeeklyReport }) {
  const totalOpenAlerts = Object.values(report.open_alerts_by_severity).reduce((a, b) => a + b, 0)

  return (
    <Card>
      <CardContent className="py-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {report.site_name ?? 'Resumen global'}
            </p>
            <p className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-500">
              <CalendarRange className="h-3.5 w-3.5" />
              {formatDate(report.window_start)} – {formatDate(report.window_end)}
            </p>
          </div>
          {report.unacknowledged_open_alerts > 0 ? (
            <StatusChip tone="critical">{report.unacknowledged_open_alerts} SIN RECONOCER</StatusChip>
          ) : (
            <StatusChip tone="ok">TODO RECONOCIDO</StatusChip>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">Servidores en línea</p>
            <p className="mt-1.5 text-xl font-semibold text-emerald-400">
              {report.servers_online}
              <span className="text-sm text-slate-500"> / {report.servers_total}</span>
            </p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <p className="flex items-center gap-1 text-xs uppercase tracking-wide text-slate-500">
              <ServerOff className="h-3 w-3" /> Desconectados
            </p>
            <p className={`mt-1.5 text-xl font-semibold ${report.servers_offline > 0 ? 'text-red-400' : 'text-slate-100'}`}>
              {report.servers_offline}
            </p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <p className="flex items-center gap-1 text-xs uppercase tracking-wide text-slate-500">
              <ArchiveX className="h-3 w-3" /> Fallos de backup
            </p>
            <p className={`mt-1.5 text-xl font-semibold ${report.backup_failures > 0 ? 'text-red-400' : 'text-slate-100'}`}>
              {report.backup_failures}
            </p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <p className="flex items-center gap-1 text-xs uppercase tracking-wide text-slate-500">
              <ShieldAlert className="h-3 w-3" /> Alertas abiertas
            </p>
            <p className="mt-1.5 text-xl font-semibold text-slate-100">{totalOpenAlerts}</p>
          </div>
        </div>

        {totalOpenAlerts > 0 && (
          <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-800 pt-4">
            {Object.entries(report.open_alerts_by_severity)
              .filter(([, count]) => count > 0)
              .map(([severity, count]) => (
                <StatusChip key={severity} tone={severityTone[severity] ?? 'neutral'}>
                  {count} {(severityLabel[severity] ?? severity).toUpperCase()}
                </StatusChip>
              ))}
          </div>
        )}

        {report.offline_servers.length > 0 && (
          <div className="mt-4 border-t border-slate-800 pt-4">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
              <ServerOff className="h-3.5 w-3.5" /> Servidores desconectados
            </p>
            <div className="flex flex-wrap gap-1.5">
              {report.offline_servers.map((s) => (
                <StatusChip key={s.id} tone="critical">
                  {s.hostname}
                </StatusChip>
              ))}
            </div>
          </div>
        )}

        {report.open_alerts.length > 0 && (
          <div className="mt-4 border-t border-slate-800 pt-4">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
              <ShieldAlert className="h-3.5 w-3.5" /> Alertas abiertas
            </p>
            <div className="flex flex-col gap-1.5">
              {report.open_alerts.map((a) => (
                <div key={a.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="text-slate-300">
                    {a.hostname ?? 'Sin servidor'} — {a.rule_name}
                    {a.value != null && <span className="text-slate-500"> ({a.value.toFixed(1)}%)</span>}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <StatusChip tone={severityTone[a.severity] ?? 'neutral'}>
                      {(severityLabel[a.severity] ?? a.severity).toUpperCase()}
                    </StatusChip>
                    {!a.acknowledged && <StatusChip tone="critical">SIN RECONOCER</StatusChip>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {report.failed_backups.length > 0 && (
          <div className="mt-4 border-t border-slate-800 pt-4">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
              <ArchiveX className="h-3.5 w-3.5" /> Backups fallidos
            </p>
            <div className="flex flex-col gap-1.5">
              {report.failed_backups.map((b) => (
                <div key={b.id} className="text-sm">
                  <span className="text-slate-300">{b.service_name}</span>
                  {b.error_message && <p className="mt-0.5 text-xs text-slate-500">{b.error_message}</p>}
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function WeeklyReportPage() {
  const { user } = useAuth()
  const [siteFilter, setSiteFilter] = useState(GLOBAL)

  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
    enabled: !!user?.is_superuser,
  })

  const { data: reports, isLoading, isError } = useQuery({
    queryKey: ['reports', 'weekly', user?.is_superuser ? siteFilter : 'own'],
    queryFn: async () =>
      (
        await api.get<WeeklyReport[]>('/reports/weekly', {
          params: user?.is_superuser && siteFilter !== GLOBAL ? { site_id: siteFilter } : undefined,
        })
      ).data,
  })

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-medium text-slate-200">Reporte semanal</h2>
          <p className="text-xs text-slate-500">
            Lo mismo que se envía por correo cada lunes — servidores, alertas y respaldos de los últimos 7 días.
          </p>
        </div>
        {user?.is_superuser && (
          <Select value={siteFilter} onValueChange={setSiteFilter}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={GLOBAL}>Resumen global</SelectItem>
              {sites?.map((site) => (
                <SelectItem key={site.id} value={site.id}>
                  {site.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {isLoading && <StatCardsSkeleton count={4} />}
      {isError && <ErrorMessage>No se pudo cargar el reporte semanal.</ErrorMessage>}
      {reports && reports.length === 0 && (
        <p className="flex items-center gap-1.5 text-sm text-slate-400">
          <AlertTriangle className="h-4 w-4" />
          No tienes ninguna sede asignada, así que no hay un reporte para mostrar.
        </p>
      )}

      <div className="flex flex-col gap-4">
        {reports?.map((report) => (
          <ReportCard key={report.site_id ?? 'global'} report={report} />
        ))}
      </div>
    </div>
  )
}
