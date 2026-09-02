import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { SERVER_USAGE_TAGS, type OSType, type Server, type ServerInput, type ServerUsageTag, type Site, type SiteUserBrief } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

const NO_SITE = '__none__'
const NO_RESPONSIBLE = '__none__'

const emptyForm: ServerInput = {
  site_id: null,
  hostname: '',
  ip_address: '',
  os_type: 'windows',
  os_version: '',
  cpu_cores: null,
  ram_mb: null,
  disk_gb: null,
  usage_tags: [],
  primary_responsible_user_id: null,
  is_synthetic_probe: false,
}

export function ServerFormDialog({ server, trigger }: { server?: Server; trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<ServerInput>(emptyForm)
  const queryClient = useQueryClient()
  const isEdit = !!server

  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
    enabled: open,
  })

  const { data: siteUsers } = useQuery({
    queryKey: ['site-users', form.site_id],
    queryFn: async () => (await api.get<SiteUserBrief[]>(`/sites/${form.site_id}/users`)).data,
    enabled: open && !!form.site_id,
  })

  useEffect(() => {
    if (!open) return
    setForm(
      server
        ? {
            site_id: server.site_id,
            hostname: server.hostname,
            ip_address: server.ip_address ?? '',
            os_type: server.os_type,
            os_version: server.os_version ?? '',
            cpu_cores: server.cpu_cores,
            ram_mb: server.ram_mb,
            disk_gb: server.disk_gb,
            usage_tags: server.usage_tags as ServerUsageTag[],
            primary_responsible_user_id: server.primary_responsible_user_id,
            is_synthetic_probe: server.is_synthetic_probe,
          }
        : emptyForm,
    )
  }, [open, server])

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = { ...form, ip_address: form.ip_address || null, os_version: form.os_version || null }
      if (isEdit) return api.patch(`/servers/${server!.id}`, payload)
      return api.post('/servers', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['servers'] })
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
          <DialogTitle>{isEdit ? 'Editar servidor' : 'Nuevo servidor'}</DialogTitle>
          <DialogDescription>Host físico o virtual gestionado por CITI.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Sede</Label>
            <Select
              value={form.site_id ?? NO_SITE}
              onValueChange={(v) =>
                setForm((f) => ({
                  ...f,
                  site_id: v === NO_SITE ? null : v,
                  primary_responsible_user_id: null,
                }))
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_SITE}>Sin asignar</SelectItem>
                {sites?.map((site) => (
                  <SelectItem key={site.id} value={site.id}>
                    {site.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Responsable</Label>
            <Select
              value={form.primary_responsible_user_id ?? NO_RESPONSIBLE}
              onValueChange={(v) => setForm((f) => ({ ...f, primary_responsible_user_id: v === NO_RESPONSIBLE ? null : v }))}
              disabled={!form.site_id}
            >
              <SelectTrigger>
                <SelectValue placeholder={form.site_id ? 'Selecciona un responsable' : 'Elige una sede primero'} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_RESPONSIBLE}>Sin asignar</SelectItem>
                {siteUsers?.map((user) => (
                  <SelectItem key={user.id} value={user.id}>
                    {user.full_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="hostname">Hostname</Label>
            <Input
              id="hostname"
              required
              value={form.hostname}
              onChange={(e) => setForm((f) => ({ ...f, hostname: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ip">IP</Label>
              <Input
                id="ip"
                value={form.ip_address ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, ip_address: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Sistema operativo</Label>
              <Select value={form.os_type} onValueChange={(v) => setForm((f) => ({ ...f, os_type: v as OSType }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="windows">Windows</SelectItem>
                  <SelectItem value="linux">Linux</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="os_version">Versión de SO</Label>
            <Input
              id="os_version"
              value={form.os_version ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, os_version: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cpu">CPU (cores)</Label>
              <Input
                id="cpu"
                type="number"
                value={form.cpu_cores ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, cpu_cores: e.target.value ? Number(e.target.value) : null }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ram">RAM (MB)</Label>
              <Input
                id="ram"
                type="number"
                value={form.ram_mb ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, ram_mb: e.target.value ? Number(e.target.value) : null }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="disk">Disco (GB)</Label>
              <Input
                id="disk"
                type="number"
                value={form.disk_gb ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, disk_gb: e.target.value ? Number(e.target.value) : null }))}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Uso (sistemas que corren en este servidor)</Label>
            <div className="grid grid-cols-3 gap-x-3 gap-y-2 rounded-md border border-slate-700 bg-slate-900 p-3">
              {SERVER_USAGE_TAGS.map((tag) => (
                <label key={tag} className="flex items-center gap-2 text-sm text-slate-200">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-slate-600 bg-slate-950 accent-amber-500"
                    checked={form.usage_tags.includes(tag)}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        usage_tags: e.target.checked ? [...f.usage_tags, tag] : f.usage_tags.filter((t) => t !== tag),
                      }))
                    }
                  />
                  {tag}
                </label>
              ))}
            </div>
          </div>
          <label className="flex items-start gap-2 text-sm text-slate-200">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-950 accent-amber-500"
              checked={form.is_synthetic_probe}
              onChange={(e) => setForm((f) => ({ ...f, is_synthetic_probe: e.target.checked }))}
            />
            <span>
              Usar como sonda de chequeos sintéticos
              <span className="block text-xs font-normal text-slate-500">
                Su Agente probará periódicamente la URL de salud de cada servicio configurado, desde la red de esta sede.
              </span>
            </span>
          </label>
          {mutation.isError && <ErrorMessage>No se pudo guardar el servidor.</ErrorMessage>}
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
