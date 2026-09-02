import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { System, SystemCriticality, SystemInput } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

const emptyForm: SystemInput = {
  name: '',
  slug: '',
  description: '',
  category: '',
  criticality: 'medium',
  repo_url: '',
  default_branch: 'main',
  repo_local_path: '',
  deploy_build_command: '',
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}

export function SystemFormDialog({ system, trigger }: { system?: System; trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<SystemInput>(emptyForm)
  const [slugTouched, setSlugTouched] = useState(!!system)
  const queryClient = useQueryClient()
  const isEdit = !!system

  useEffect(() => {
    if (!open) return
    setForm(
      system
        ? {
            name: system.name,
            slug: system.slug,
            description: system.description ?? '',
            category: system.category ?? '',
            criticality: system.criticality,
            repo_url: system.repo_url ?? '',
            default_branch: system.default_branch ?? 'main',
            repo_local_path: system.repo_local_path ?? '',
            deploy_build_command: system.deploy_build_command ?? '',
          }
        : emptyForm,
    )
    setSlugTouched(!!system)
  }, [open, system])

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = {
        ...form,
        description: form.description || null,
        category: form.category || null,
        repo_url: form.repo_url || null,
        repo_local_path: form.repo_local_path || null,
        deploy_build_command: form.deploy_build_command || null,
      }
      if (isEdit) return api.patch(`/systems/${system!.id}`, payload)
      return api.post('/systems', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systems'] })
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
          <DialogTitle>{isEdit ? 'Editar sistema' : 'Nuevo sistema'}</DialogTitle>
          <DialogDescription>Ficha técnica del activo tecnológico institucional.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Nombre</Label>
            <Input
              id="name"
              required
              value={form.name}
              onChange={(e) => {
                const name = e.target.value
                setForm((f) => ({ ...f, name, slug: slugTouched ? f.slug : slugify(name) }))
              }}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="slug">Slug</Label>
            <Input
              id="slug"
              required
              value={form.slug}
              onChange={(e) => {
                setSlugTouched(true)
                setForm((f) => ({ ...f, slug: e.target.value }))
              }}
              disabled={isEdit}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="description">Descripción</Label>
            <Textarea
              id="description"
              value={form.description ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="category">Categoría</Label>
              <Input
                id="category"
                value={form.category ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Criticidad</Label>
              <Select
                value={form.criticality}
                onValueChange={(v) => setForm((f) => ({ ...f, criticality: v as SystemCriticality }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Baja</SelectItem>
                  <SelectItem value="medium">Media</SelectItem>
                  <SelectItem value="high">Alta</SelectItem>
                  <SelectItem value="critical">Crítica</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="repo_url">Repositorio Git</Label>
              <Input
                id="repo_url"
                placeholder="https://github.com/org/repo"
                value={form.repo_url ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, repo_url: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="default_branch">Rama</Label>
              <Input
                id="default_branch"
                placeholder="main"
                value={form.default_branch ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, default_branch: e.target.value }))}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="repo_local_path">Ruta local del repositorio (en el servidor)</Label>
            <Input
              id="repo_local_path"
              placeholder="E:\PROGRAMACION\Sistema"
              value={form.repo_local_path ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, repo_local_path: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="deploy_build_command">Comando de build post-pull (opcional)</Label>
            <Textarea
              id="deploy_build_command"
              placeholder="cd backend && venv\Scripts\pip install -r requirements.txt && cd ..\frontend && npm install && npm run build"
              value={form.deploy_build_command ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, deploy_build_command: e.target.value }))}
            />
          </div>
          {mutation.isError && <ErrorMessage>No se pudo guardar el sistema.</ErrorMessage>}
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
