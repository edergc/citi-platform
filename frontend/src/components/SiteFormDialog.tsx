import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Site, SiteInput } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

const emptyForm: SiteInput = { name: '', code: '', address: '', timezone: 'America/Lima' }

export function SiteFormDialog({ site, trigger }: { site?: Site; trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<SiteInput>(emptyForm)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const isEdit = !!site

  useEffect(() => {
    if (!open) return
    setError(null)
    setForm(
      site
        ? { name: site.name, code: site.code, address: site.address ?? '', timezone: site.timezone }
        : emptyForm,
    )
  }, [open, site])

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = { ...form, address: form.address || null }
      if (isEdit) return api.patch(`/sites/${site!.id}`, payload)
      return api.post('/sites', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites'] })
      setOpen(false)
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'No se pudo guardar la sede.')
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar sede' : 'Nueva sede'}</DialogTitle>
          <DialogDescription>Sedes o locales de la Corte Superior de Justicia de Lima.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="site-name">Nombre</Label>
            <Input
              id="site-name"
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="site-code">Código</Label>
            <Input
              id="site-code"
              required
              value={form.code}
              onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="site-address">Dirección (opcional)</Label>
            <Input
              id="site-address"
              value={form.address ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="site-tz">Zona horaria</Label>
            <Input
              id="site-tz"
              required
              value={form.timezone}
              onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
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
