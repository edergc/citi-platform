import { useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ConfigEntry, ConfigEntryInput } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

export function ConfigEntryDialog({
  serviceId,
  entry,
  trigger,
}: {
  serviceId: string
  entry?: ConfigEntry
  trigger: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const isEdit = !!entry
  const [form, setForm] = useState<Omit<ConfigEntryInput, 'service_id'>>({
    environment_code: 'prod',
    key: entry?.key ?? '',
    value: '',
    is_secret: entry?.is_secret ?? false,
    description: entry?.description ?? '',
  })
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async () => api.post('/config-entries', { ...form, service_id: serviceId, description: form.description || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config-entries', serviceId] })
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
          <DialogTitle>{isEdit ? `Editar ${entry.key}` : 'Nueva variable de configuración'}</DialogTitle>
          <DialogDescription>
            Los valores marcados como secreto se guardan cifrados y nunca se muestran de nuevo en texto plano.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="key">Clave</Label>
            <Input
              id="key"
              required
              disabled={isEdit}
              placeholder="DB_HOST, SMTP_PORT, JWT_SECRET…"
              value={form.key}
              onChange={(e) => setForm((f) => ({ ...f, key: e.target.value.toUpperCase() }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="value">Valor {isEdit && '(escribe uno nuevo para reemplazarlo)'}</Label>
            <Input
              id="value"
              required
              type={form.is_secret ? 'password' : 'text'}
              value={form.value}
              onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))}
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              id="is_secret"
              type="checkbox"
              checked={form.is_secret}
              onChange={(e) => setForm((f) => ({ ...f, is_secret: e.target.checked }))}
              className="h-4 w-4 rounded border-slate-700 bg-slate-900"
            />
            <Label htmlFor="is_secret">Es un secreto (se cifra, nunca se vuelve a mostrar)</Label>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="description">Descripción</Label>
            <Textarea
              id="description"
              value={form.description ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          {mutation.isError && <ErrorMessage>No se pudo guardar la variable.</ErrorMessage>}
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
