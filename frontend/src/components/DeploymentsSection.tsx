import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { DeployCheckResult, Deployment, DeploymentStatus, System } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ErrorMessage } from '@/components/ui/error-message'

const statusVariant: Record<DeploymentStatus, 'success' | 'warning' | 'danger' | 'default'> = {
  success: 'success',
  rolled_back: 'warning',
  failed: 'danger',
  pending: 'default',
  running: 'default',
}

export function DeploymentsSection({ system }: { system: System }) {
  const queryClient = useQueryClient()
  const [checkResult, setCheckResult] = useState<DeployCheckResult | null>(null)

  const configured = Boolean(system.repo_url && system.repo_local_path)

  const { data: deployments } = useQuery({
    queryKey: ['deployments', system.id],
    queryFn: async () => (await api.get<Deployment[]>(`/systems/${system.id}/deployments`)).data,
    enabled: configured,
  })

  const check = useMutation({
    mutationFn: async () => (await api.post<DeployCheckResult>(`/systems/${system.id}/deploy/check`)).data,
    onSuccess: (data) => setCheckResult(data),
  })

  const deploy = useMutation({
    mutationFn: async () => api.post(`/systems/${system.id}/deploy`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments', system.id] })
      queryClient.invalidateQueries({ queryKey: ['versions', system.id] })
      queryClient.invalidateQueries({ queryKey: ['services'] })
      setCheckResult(null)
    },
  })

  return (
    <div>
      <h3 className="mb-4 text-base font-medium text-slate-200">Centro de Despliegues</h3>

      {!configured && (
        <p className="text-xs text-slate-500">
          Configura "Repositorio Git" y "Ruta local del repositorio" editando el sistema para habilitar despliegues.
        </p>
      )}

      {configured && (
        <>
          <div className="mb-4 flex items-center gap-2 text-xs text-slate-500">
            <span>
              {system.repo_url} @ {system.default_branch}
            </span>
            <span>·</span>
            <span className="font-mono">{system.repo_local_path}</span>
          </div>

          <div className="mb-4 flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={check.isPending} onClick={() => check.mutate()}>
              {check.isPending ? 'Verificando…' : 'Verificar actualizaciones'}
            </Button>
            <Button
              size="sm"
              disabled={!checkResult || checkResult.is_dirty || checkResult.commits_behind === 0 || deploy.isPending}
              onClick={() => {
                if (confirm(`¿Desplegar ${checkResult?.commits_behind} commit(s) nuevo(s) en ${system.name}?`))
                  deploy.mutate()
              }}
            >
              {deploy.isPending ? 'Desplegando…' : 'Desplegar'}
            </Button>
          </div>

          {check.isError && <ErrorMessage className="mb-3 text-xs">No se pudo verificar el estado del repositorio.</ErrorMessage>}

          {checkResult && (
            <div className="mb-4 rounded-md border border-slate-800 p-3 text-xs">
              {checkResult.error && <ErrorMessage>{checkResult.error}</ErrorMessage>}
              {checkResult.is_dirty && (
                <div className="text-amber-400">
                  <p className="font-medium">
                    El árbol de trabajo tiene {checkResult.dirty_files.length} archivo(s) sin confirmar — despliegue bloqueado.
                  </p>
                  <ul className="mt-1 list-inside list-disc font-mono text-slate-400">
                    {checkResult.dirty_files.slice(0, 10).map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                  <p className="mt-1 text-slate-500">Resuelve esto directamente en el servidor (commit o descarta los cambios) antes de desplegar desde CITI.</p>
                </div>
              )}
              {!checkResult.is_dirty && !checkResult.error && (
                <p className="text-slate-400">
                  {checkResult.commits_behind === 0
                    ? 'Ya está al día con el repositorio remoto.'
                    : `${checkResult.commits_behind} commit(s) atrás de origin/${system.default_branch}.`}
                  {checkResult.current_commit && (
                    <span className="ml-2 font-mono text-slate-500">actual: {checkResult.current_commit.slice(0, 8)}</span>
                  )}
                </p>
              )}
            </div>
          )}

          {deploy.isError && <ErrorMessage className="mb-3 text-xs">No se pudo ejecutar el despliegue.</ErrorMessage>}

          {deployments && deployments.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-slate-800">
              <table className="w-full text-xs">
                <thead className="bg-slate-900/60 text-left uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">Fecha</th>
                    <th className="px-4 py-2 font-medium">Estado</th>
                    <th className="px-4 py-2 font-medium">Log</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {deployments.map((d) => (
                    <tr key={d.id}>
                      <td className="px-4 py-2 text-slate-400">
                        {d.started_at ? new Date(d.started_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-2">
                        <Badge variant={statusVariant[d.status]}>{d.status}</Badge>
                      </td>
                      <td className="max-w-md truncate px-4 py-2 font-mono text-slate-500">{d.log_output ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
