import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { MaintenanceScope, MaintenanceWindow, MaintenanceWindowInput, Server, Site } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

/** datetime-local inputs work in the browser's local timezone as a naive "YYYY-MM-DDTHH:mm"
 * string — no timezone suffix. new Date(...) on that string parses it as local time, and
 * .toISOString() converts to UTC for the API; the reverse slice(0, 16) drops seconds/ms
 * for round-tripping an existing ISO value back into the input. */
function toLocalInput(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function defaultStart(): string {
  return toLocalInput(new Date().toISOString())
}

function defaultEnd(): string {
  return toLocalInput(new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString())
}

type FormState = {
  scope_type: MaintenanceScope
  scope_id: string
  reason: string
  description: string
  starts_at: string
  ends_at: string
}

function emptyForm(defaultScope?: { type: MaintenanceScope; id: string }): FormState {
  return {
    scope_type: defaultScope?.type ?? 'server',
    scope_id: defaultScope?.id ?? '',
    reason: '',
    description: '',
    starts_at: defaultStart(),
    ends_at: defaultEnd(),
  }
}

export function MaintenanceWindowFormDialog({
  window: editWindow,
  trigger,
  defaultScope,
}: {
  window?: MaintenanceWindow
  trigger: ReactNode
  defaultScope?: { type: MaintenanceScope; id: string; label: string }
}) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<FormState>(emptyForm(defaultScope))
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const isEdit = !!editWindow

  const { data: servers } = useQuery({
    queryKey: ['servers'],
    queryFn: async () => (await api.get<Server[]>('/servers')).data,
    enabled: open && form.scope_type === 'server' && !defaultScope,
  })
  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
    enabled: open && form.scope_type === 'site',
  })

  useEffect(() => {
    if (!open) return
    setError(null)
    if (editWindow) {
      setForm({
        scope_type: editWindow.scope_type,
        scope_id: editWindow.scope_id,
        reason: editWindow.reason,
        description: editWindow.description ?? '',
        starts_at: toLocalInput(editWindow.starts_at),
        ends_at: toLocalInput(editWindow.ends_at),
      })
    } else {
      setForm(emptyForm(defaultScope))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editWindow])

  const mutation = useMutation({
    mutationFn: async () => {
      if (isEdit) {
        return api.patch(`/maintenance-windows/${editWindow!.id}`, {
          reason: form.reason,
          description: form.description || null,
          ends_at: new Date(form.ends_at).toISOString(),
        })
      }
      const payload: MaintenanceWindowInput = {
        scope_type: form.scope_type,
        scope_id: form.scope_id,
        reason: form.reason,
        description: form.description || null,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
      }
      return api.post('/maintenance-windows', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenance-windows'] })
      queryClient.invalidateQueries({ queryKey: ['servers'] })
      setOpen(false)
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'No se pudo guardar la ventana de mantenimiento.')
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!isEdit && !form.scope_id) {
      setError(form.scope_type === 'server' ? 'Selecciona un servidor.' : 'Selecciona una sede.')
      return
    }
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar ventana de mantenimiento' : 'Programar mantenimiento'}</DialogTitle>
          <DialogDescription>
            Mientras esté activa, no se enviarán notificaciones (correo ni campanita) por caídas o alertas del alcance
            elegido — las alertas de umbral se siguen registrando en el historial, solo no avisan.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {!isEdit && (
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label>Alcance</Label>
                <Select
                  value={form.scope_type}
                  onValueChange={(v) => setForm((f) => ({ ...f, scope_type: v as MaintenanceScope, scope_id: '' }))}
                  disabled={!!defaultScope}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="server">Un servidor</SelectItem>
                    <SelectItem value="site">Toda una sede</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>{form.scope_type === 'server' ? 'Servidor' : 'Sede'}</Label>
                {defaultScope ? (
                  <Input disabled value={defaultScope.label} />
                ) : form.scope_type === 'server' ? (
                  <Select value={form.scope_id} onValueChange={(v) => setForm((f) => ({ ...f, scope_id: v }))}>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecciona…" />
                    </SelectTrigger>
                    <SelectContent>
                      {servers?.map((server) => (
                        <SelectItem key={server.id} value={server.id}>
                          {server.hostname}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Select value={form.scope_id} onValueChange={(v) => setForm((f) => ({ ...f, scope_id: v }))}>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecciona…" />
                    </SelectTrigger>
                    <SelectContent>
                      {sites?.map((site) => (
                        <SelectItem key={site.id} value={site.id}>
                          {site.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
          )}

          {isEdit && (
            <p className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 text-xs text-slate-400">
              Alcance: {editWindow!.scope_type === 'server' ? 'servidor' : 'sede'} — {editWindow!.scope_label}. El alcance y el
              inicio no se pueden editar; cancela y crea una nueva ventana si necesitas cambiarlos.
            </p>
          )}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="mw-reason">Motivo</Label>
            <Input
              id="mw-reason"
              required
              placeholder="Ej: Actualización de Windows Server"
              value={form.reason}
              onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mw-start">Inicio</Label>
              <Input
                id="mw-start"
                type="datetime-local"
                required
                disabled={isEdit}
                value={form.starts_at}
                onChange={(e) => setForm((f) => ({ ...f, starts_at: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mw-end">Fin</Label>
              <Input
                id="mw-end"
                type="datetime-local"
                required
                value={form.ends_at}
                onChange={(e) => setForm((f) => ({ ...f, ends_at: e.target.value }))}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="mw-description">Notas (opcional)</Label>
            <Textarea
              id="mw-description"
              placeholder="Detalles del trabajo planificado…"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>

          {error && <ErrorMessage>{error}</ErrorMessage>}
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
