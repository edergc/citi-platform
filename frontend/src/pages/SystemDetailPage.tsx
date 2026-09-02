import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Cog,
  FileText,
  GitBranch,
  HardDrive,
  Package,
  Rocket,
  SlidersHorizontal,
  Trash2,
} from 'lucide-react'
import { api } from '@/lib/api'
import type { Service, ServiceStatus, System } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { DetailPageSkeleton } from '@/components/ui/skeleton'
import { StatusChip } from '@/components/ui/status-chip'
import { cn } from '@/lib/utils'
import { SystemFormDialog } from '@/components/SystemFormDialog'
import { ServiceFormDialog } from '@/components/ServiceFormDialog'
import { ServiceActions } from '@/components/ServiceActions'
import { BackupsSection } from '@/components/BackupsSection'
import { ConfigSection } from '@/components/ConfigSection'
import { VersionsSection } from '@/components/VersionsSection'
import { DeploymentsSection } from '@/components/DeploymentsSection'
import { DocumentsSection } from '@/components/DocumentsSection'
import { InventorySection } from '@/components/InventorySection'
import { SyntheticChecksSection } from '@/components/SyntheticChecksSection'

const serviceStatusTone: Record<ServiceStatus, 'ok' | 'neutral' | 'warning'> = {
  running: 'ok',
  stopped: 'neutral',
  degraded: 'warning',
  unknown: 'neutral',
}

const statusTone: Record<System['status'], 'ok' | 'warning' | 'neutral'> = {
  active: 'ok',
  maintenance: 'warning',
  retired: 'neutral',
}

const criticalityVariant: Record<System['criticality'], 'default' | 'info' | 'warning' | 'danger'> = {
  low: 'default',
  medium: 'info',
  high: 'warning',
  critical: 'danger',
}

type Tab = 'services' | 'deployments' | 'versions' | 'config' | 'backups' | 'documents' | 'inventory'

const tabs: { key: Tab; label: string; icon: typeof Cog }[] = [
  { key: 'services', label: 'Servicios', icon: Cog },
  { key: 'deployments', label: 'Despliegues', icon: Rocket },
  { key: 'versions', label: 'Versiones', icon: GitBranch },
  { key: 'config', label: 'Configuración', icon: SlidersHorizontal },
  { key: 'backups', label: 'Backups', icon: HardDrive },
  { key: 'documents', label: 'Documentos', icon: FileText },
  { key: 'inventory', label: 'Inventario', icon: Package },
]

function ServicesTab({ system, services }: { system: System; services: Service[] | undefined }) {
  const queryClient = useQueryClient()
  const deleteService = useMutation({
    mutationFn: async (serviceId: string) => api.delete(`/services/${serviceId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['services', system.id] }),
  })

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-base font-medium text-slate-200">Control de Servicios</h3>
        <ServiceFormDialog systemId={system.id} trigger={<Button size="sm">+ Nuevo servicio</Button>} />
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Servicio</th>
              <th className="px-4 py-2 font-medium">Tipo</th>
              <th className="px-4 py-2 font-medium">Control</th>
              <th className="px-4 py-2 font-medium">Puerto</th>
              <th className="px-4 py-2 font-medium">Estado</th>
              <th className="px-4 py-2 font-medium">Acciones</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {services?.map((service) => (
              <tr key={service.id}>
                <td className="px-4 py-2 text-slate-100">
                  {service.name}
                  {service.control_identifier && (
                    <div className="text-xs text-slate-500">{service.control_identifier}</div>
                  )}
                </td>
                <td className="px-4 py-2 text-slate-400">{service.type}</td>
                <td className="px-4 py-2 text-slate-400">{service.control_strategy}</td>
                <td className="px-4 py-2 text-slate-400">{service.port ?? '—'}</td>
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
                <td className="px-4 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <ServiceFormDialog
                      systemId={system.id}
                      service={service}
                      trigger={<Button variant="ghost" size="sm">Editar</Button>}
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (confirm(`¿Eliminar el servicio "${service.name}"?`)) deleteService.mutate(service.id)
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {services && services.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-sm text-slate-500">
                  Este sistema todavía no tiene servicios registrados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <SyntheticChecksSection services={services ?? []} />
    </div>
  )
}

export function SystemDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('services')

  const { data: system, isLoading } = useQuery({
    queryKey: ['systems', id],
    queryFn: async () => (await api.get<System>(`/systems/${id}`)).data,
    enabled: !!id,
  })

  const { data: services } = useQuery({
    queryKey: ['services', id],
    queryFn: async () => (await api.get<Service[]>('/services', { params: { system_id: id } })).data,
    enabled: !!id,
  })

  const deleteSystem = useMutation({
    mutationFn: async () => api.delete(`/systems/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systems'] })
      navigate('/')
    },
  })

  if (isLoading || !system) {
    return <DetailPageSkeleton />
  }

  const runningCount = services?.filter((s) => s.status === 'running').length ?? 0

  return (
    <div>
      <Link to="/" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200">
        <ArrowLeft className="h-4 w-4" /> Centro de Aplicaciones
      </Link>

      <Card className="mb-6">
        <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold text-slate-100">{system.name}</h2>
              <StatusChip tone={statusTone[system.status]}>{system.status.toUpperCase()}</StatusChip>
              <Badge variant={criticalityVariant[system.criticality]}>{system.criticality}</Badge>
              {system.category && <Badge variant="default">{system.category}</Badge>}
            </div>
            <p className="mt-1.5 text-sm text-slate-400">{system.description ?? 'Sin descripción'}</p>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
              <span>slug: {system.slug}</span>
              {services && (
                <span>
                  {services.length} {services.length === 1 ? 'servicio' : 'servicios'} · {runningCount} en ejecución
                </span>
              )}
              {system.repo_url && (
                <span className="flex items-center gap-1">
                  <GitBranch className="h-3.5 w-3.5" />
                  {system.repo_url} ({system.default_branch})
                </span>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <SystemFormDialog system={system} trigger={<Button variant="outline" size="sm">Editar</Button>} />
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                if (confirm(`¿Eliminar "${system.name}" y todos sus servicios?`)) deleteSystem.mutate()
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="mb-6 flex gap-1 overflow-x-auto border-b border-slate-800">
        {tabs.map((t) => {
          const Icon = t.icon
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'flex shrink-0 items-center gap-1.5 px-4 py-2 text-sm transition-colors',
                tab === t.key ? 'border-b-2 border-amber-500 text-slate-100' : 'text-slate-400 hover:text-slate-200',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
            </button>
          )
        })}
      </div>

      {tab === 'services' && <ServicesTab system={system} services={services} />}
      {tab === 'deployments' && <DeploymentsSection system={system} />}
      {tab === 'versions' && <VersionsSection system={system} />}
      {tab === 'config' &&
        (services && services.length > 0 ? (
          <ConfigSection services={services} />
        ) : (
          <p className="text-sm text-slate-500">Registra al menos un servicio para configurar variables.</p>
        ))}
      {tab === 'backups' &&
        (services && services.length > 0 ? (
          <BackupsSection services={services} />
        ) : (
          <p className="text-sm text-slate-500">Registra al menos un servicio para configurar respaldos.</p>
        ))}
      {tab === 'documents' && <DocumentsSection systemId={system.id} />}
      {tab === 'inventory' && <InventorySection systemId={system.id} />}
    </div>
  )
}
