import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { System, SystemVersion, VersionStatus } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { VersionDialog } from '@/components/VersionDialog'

const statusVariant: Record<VersionStatus, 'success' | 'default' | 'warning'> = {
  active: 'success',
  deprecated: 'default',
  rolled_back: 'warning',
}

export function VersionsSection({ system }: { system: System }) {
  const systemId = system.id
  const queryClient = useQueryClient()
  const canDeployRollback = Boolean(system.repo_url && system.repo_local_path)

  const { data: versions } = useQuery({
    queryKey: ['versions', systemId],
    queryFn: async () => (await api.get<SystemVersion[]>(`/systems/${systemId}/versions`)).data,
  })

  const invalidateAfterRollback = () => {
    queryClient.invalidateQueries({ queryKey: ['versions', systemId] })
    queryClient.invalidateQueries({ queryKey: ['deployments', systemId] })
    queryClient.invalidateQueries({ queryKey: ['services'] })
  }

  const bookkeepingRollback = useMutation({
    mutationFn: async (versionId: string) => api.post(`/versions/${versionId}/rollback`),
    onSuccess: invalidateAfterRollback,
  })

  const deployRollback = useMutation({
    mutationFn: async (versionId: string) => api.post(`/systems/${systemId}/deploy/rollback/${versionId}`),
    onSuccess: invalidateAfterRollback,
  })

  const rollback = canDeployRollback ? deployRollback : bookkeepingRollback

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-base font-medium text-slate-200">Gestión de Versiones</h3>
        <VersionDialog systemId={systemId} trigger={<Button size="sm">+ Registrar versión</Button>} />
      </div>

      {versions && versions.length === 0 && <p className="text-xs text-slate-500">Sin versiones registradas.</p>}

      {versions && versions.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Versión</th>
                <th className="px-4 py-2 font-medium">Rama / Commit</th>
                <th className="px-4 py-2 font-medium">Estado</th>
                <th className="px-4 py-2 font-medium">Fecha</th>
                <th className="px-4 py-2 font-medium">Notas</th>
                <th className="px-4 py-2 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {versions.map((v) => (
                <tr key={v.id}>
                  <td className="px-4 py-2 font-mono text-slate-100">{v.version_number}</td>
                  <td className="px-4 py-2 text-slate-400">
                    {v.git_branch ?? '—'} {v.git_commit_hash && `@ ${v.git_commit_hash.slice(0, 8)}`}
                  </td>
                  <td className="px-4 py-2">
                    <Badge variant={statusVariant[v.status]}>{v.status}</Badge>
                  </td>
                  <td className="px-4 py-2 text-slate-400">
                    {v.released_at ? new Date(v.released_at).toLocaleString() : '—'}
                  </td>
                  <td className="max-w-xs truncate px-4 py-2 text-slate-400">{v.release_notes ?? '—'}</td>
                  <td className="px-4 py-2 text-right">
                    {v.status !== 'active' && (!canDeployRollback || v.git_commit_hash) && (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={rollback.isPending}
                        onClick={() => {
                          const message = canDeployRollback
                            ? `¿Volver "${v.version_number}" (commit ${v.git_commit_hash?.slice(0, 8)}) a producción? Esto hace checkout, corre el build y reinicia los servicios.`
                            : `¿Marcar "${v.version_number}" como versión activa? Esto no reinstala código, solo registra el rollback.`
                          if (confirm(message)) rollback.mutate(v.id)
                        }}
                      >
                        {rollback.isPending ? 'Restaurando…' : 'Rollback'}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
