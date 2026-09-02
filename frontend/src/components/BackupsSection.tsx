import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { BackupJob, BackupRunPage, RunStatus, Service } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Pagination } from '@/components/ui/pagination'
import { BackupJobDialog } from '@/components/BackupJobDialog'
import { ErrorMessage } from '@/components/ui/error-message'

const RUNS_PAGE_SIZE = 10

function formatBytes(bytes: number | null) {
  if (bytes == null) return '—'
  const mb = bytes / (1024 * 1024)
  return mb < 1 ? `${Math.round(bytes / 1024)} KB` : `${mb.toFixed(1)} MB`
}

const runStatusVariant: Record<RunStatus, 'success' | 'warning' | 'danger' | 'default'> = {
  success: 'success',
  failed: 'danger',
  pending: 'warning',
  running: 'warning',
}

function BackupJobRow({ job }: { job: BackupJob }) {
  const queryClient = useQueryClient()
  const [runsPage, setRunsPage] = useState(1)
  const { data: runs } = useQuery({
    queryKey: ['backup-runs', job.id, runsPage],
    queryFn: async () =>
      (
        await api.get<BackupRunPage>(`/backup-jobs/${job.id}/runs`, {
          params: { limit: RUNS_PAGE_SIZE, offset: (runsPage - 1) * RUNS_PAGE_SIZE },
        })
      ).data,
  })
  const runsTotalPages = Math.max(1, Math.ceil((runs?.total ?? 0) / RUNS_PAGE_SIZE))

  const runNow = useMutation({
    mutationFn: async () => api.post(`/backup-jobs/${job.id}/run`),
    onSuccess: () => {
      setRunsPage(1)
      queryClient.invalidateQueries({ queryKey: ['backup-runs', job.id] })
    },
  })

  const restore = useMutation({
    mutationFn: async (runId: string) => api.post(`/backup-runs/${runId}/restore`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backup-runs', job.id] }),
  })

  return (
    <div className="rounded-md border border-slate-800 p-3">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-sm text-slate-200">{job.source_path}</p>
          <p className="truncate text-xs text-slate-500">
            → {job.storage_path} · {job.type} · retención {job.retention_days}d
          </p>
        </div>
        <Button size="sm" disabled={runNow.isPending} onClick={() => runNow.mutate()}>
          {runNow.isPending ? 'Ejecutando…' : 'Ejecutar ahora'}
        </Button>
      </div>

      {runs && runs.items.length > 0 && (
        <>
          <table className="mt-3 w-full text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="pb-1 text-left font-medium">Fecha</th>
                <th className="pb-1 text-left font-medium">Estado</th>
                <th className="pb-1 text-left font-medium">Tamaño</th>
                <th className="pb-1 text-left font-medium">SHA256</th>
                <th className="pb-1 text-left font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {runs.items.map((run) => (
                <tr key={run.id}>
                  <td className="py-1 text-slate-400">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                  </td>
                  <td className="py-1">
                    <Badge variant={runStatusVariant[run.status]}>{run.status}</Badge>
                  </td>
                  <td className="py-1 text-slate-400">{formatBytes(run.size_bytes)}</td>
                  <td className="py-1 font-mono text-slate-500">
                    {run.sha256_hash ? `${run.sha256_hash.slice(0, 12)}…` : '—'}
                  </td>
                  <td className="py-1 text-right">
                    {run.status === 'success' && (
                      <Button variant="ghost" size="sm" disabled={restore.isPending} onClick={() => restore.mutate(run.id)}>
                        Restaurar
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {runsTotalPages > 1 && (
            <div className="mt-2">
              <Pagination page={runsPage} totalPages={runsTotalPages} onPageChange={setRunsPage} />
            </div>
          )}
        </>
      )}

      {runNow.isError && <ErrorMessage className="mt-2 text-xs">No se pudo ejecutar el respaldo.</ErrorMessage>}
      {restore.isError && <ErrorMessage className="mt-2 text-xs">No se pudo restaurar.</ErrorMessage>}
      {restore.isSuccess && (
        <p className="mt-2 text-xs text-emerald-400">Restaurado en una carpeta separada junto al origen (no sobrescribe nada).</p>
      )}
    </div>
  )
}

export function BackupsSection({ services }: { services: Service[] }) {
  const { data: allJobs } = useQuery({
    queryKey: ['backup-jobs'],
    queryFn: async () => (await api.get<BackupJob[]>('/backup-jobs')).data,
  })

  const serviceIds = new Set(services.map((s) => s.id))
  const jobs = allJobs?.filter((j) => serviceIds.has(j.service_id)) ?? []

  return (
    <div>
      <h3 className="mb-4 text-base font-medium text-slate-200">Centro de Respaldos</h3>
      <div className="flex flex-col gap-6">
        {services.map((service) => {
          const serviceJobs = jobs.filter((j) => j.service_id === service.id)
          return (
            <div key={service.id}>
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm font-medium text-slate-300">{service.name}</p>
                <BackupJobDialog
                  serviceId={service.id}
                  trigger={
                    <Button variant="outline" size="sm">
                      + Nuevo respaldo
                    </Button>
                  }
                />
              </div>
              {serviceJobs.length === 0 && <p className="text-xs text-slate-500">Sin respaldos configurados.</p>}
              <div className="flex flex-col gap-2">
                {serviceJobs.map((job) => (
                  <BackupJobRow key={job.id} job={job} />
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
