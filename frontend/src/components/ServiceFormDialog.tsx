import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ControlStrategy, Server, Service, ServiceInput, ServiceType } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

const serviceTypes: ServiceType[] = [
  'frontend',
  'backend',
  'database',
  'cache',
  'proxy',
  'windows_service',
  'pm2_process',
  'ftp',
  'smtp',
  'cron_job',
  'other',
]

const controlStrategies: ControlStrategy[] = ['pm2', 'windows_service', 'systemd', 'docker', 'script']

function emptyForm(systemId: string): ServiceInput {
  return {
    system_id: systemId,
    server_id: null,
    name: '',
    type: 'backend',
    control_strategy: 'pm2',
    control_identifier: '',
    port: null,
    health_check_url: '',
  }
}

export function ServiceFormDialog({
  systemId,
  service,
  trigger,
}: {
  systemId: string
  service?: Service
  trigger: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<ServiceInput>(emptyForm(systemId))
  const queryClient = useQueryClient()
  const isEdit = !!service

  const { data: servers } = useQuery({
    queryKey: ['servers'],
    queryFn: async () => (await api.get<Server[]>('/servers')).data,
    enabled: open,
  })

  useEffect(() => {
    if (!open) return
    setForm(
      service
        ? {
            system_id: systemId,
            server_id: service.server_id,
            name: service.name,
            type: service.type,
            control_strategy: service.control_strategy,
            control_identifier: service.control_identifier ?? '',
            port: service.port,
            health_check_url: service.health_check_url ?? '',
          }
        : emptyForm(systemId),
    )
  }, [open, service, systemId])

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = {
        ...form,
        control_identifier: form.control_identifier || null,
        health_check_url: form.health_check_url || null,
      }
      if (isEdit) return api.patch(`/services/${service!.id}`, payload)
      return api.post('/services', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services', systemId] })
      setOpen(false)
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar servicio' : 'Nuevo servicio'}</DialogTitle>
          <DialogDescription>Componente controlable dentro del sistema (frontend, backend, etc.).</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="svc-name">Nombre</Label>
            <Input
              id="svc-name"
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label>Tipo</Label>
              <Select value={form.type} onValueChange={(v) => setForm((f) => ({ ...f, type: v as ServiceType }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {serviceTypes.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Estrategia de control</Label>
              <Select
                value={form.control_strategy}
                onValueChange={(v) => setForm((f) => ({ ...f, control_strategy: v as ControlStrategy }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {controlStrategies.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Servidor</Label>
            <Select
              value={form.server_id ?? 'none'}
              onValueChange={(v) => setForm((f) => ({ ...f, server_id: v === 'none' ? null : v }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Sin asignar</SelectItem>
                {servers?.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.hostname}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="port">Puerto</Label>
              <Input
                id="port"
                type="number"
                value={form.port ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, port: e.target.value ? Number(e.target.value) : null }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="identifier">Ruta / identificador</Label>
              <Input
                id="identifier"
                placeholder="E:\PROGRAMACION\..."
                value={form.control_identifier ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, control_identifier: e.target.value }))}
              />
            </div>
          </div>
          {mutation.isError && <ErrorMessage>No se pudo guardar el servicio.</ErrorMessage>}
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Guardando…' : 'Guardar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
