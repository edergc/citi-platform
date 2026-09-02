import { useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { BackupJobInput, BackupType } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

export function BackupJobDialog({ serviceId, trigger }: { serviceId: string; trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<Omit<BackupJobInput, 'service_id'>>({
    type: 'files',
    source_path: '',
    storage_path: '',
    retention_days: 30,
    schedule_cron: '',
  })
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async () =>
      api.post('/backup-jobs', {
        ...form,
        service_id: serviceId,
        schedule_cron: form.schedule_cron?.trim() ? form.schedule_cron.trim() : null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backup-jobs'] })
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
          <DialogTitle>Nuevo job de respaldo</DialogTitle>
          <DialogDescription>
            El Agente CITI comprime la carpeta de origen (excluyendo node_modules/venv/.git) y la guarda con hash SHA256.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Tipo</Label>
            <Select value={form.type} onValueChange={(v) => setForm((f) => ({ ...f, type: v as BackupType }))}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="files">Archivos</SelectItem>
                <SelectItem value="database">Base de datos</SelectItem>
                <SelectItem value="full">Completo</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {form.type === 'database' ? (
            <p className="text-xs text-slate-500">
              La conexión se toma de las credenciales guardadas en la configuración del servicio (no se necesita ruta de
              origen).
            </p>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="source_path">Ruta de origen</Label>
              <Input
                id="source_path"
                placeholder="E:\PROGRAMACION\Sistema\backend"
                required
                value={form.source_path}
                onChange={(e) => setForm((f) => ({ ...f, source_path: e.target.value }))}
              />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="storage_path">Ruta de almacenamiento</Label>
            <Input
              id="storage_path"
              placeholder="E:\PROGRAMACION\Citi-Platform\backups\sistema-backend"
              required
              value={form.storage_path}
              onChange={(e) => setForm((f) => ({ ...f, storage_path: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="retention">Retención (días)</Label>
            <Input
              id="retention"
              type="number"
              value={form.retention_days}
              onChange={(e) => setForm((f) => ({ ...f, retention_days: Number(e.target.value) }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="schedule_cron">Programación (cron, opcional)</Label>
            <Input
              id="schedule_cron"
              placeholder="0 2 * * *"
              value={form.schedule_cron ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, schedule_cron: e.target.value }))}
            />
            <p className="text-xs text-slate-500">
              Vacío = solo manual. Ejemplo: <code className="font-mono">0 2 * * *</code> = todos los días a las 2:00 a.m.
            </p>
          </div>
          {mutation.isError && <ErrorMessage>No se pudo crear el job de respaldo.</ErrorMessage>}
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
