import { useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { SystemVersionInput } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ErrorMessage } from '@/components/ui/error-message'

export function VersionDialog({ systemId, trigger }: { systemId: string; trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<SystemVersionInput>({
    version_number: '',
    git_commit_hash: '',
    git_branch: '',
    release_notes: '',
  })
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async () =>
      api.post(`/systems/${systemId}/versions`, {
        ...form,
        git_commit_hash: form.git_commit_hash || null,
        git_branch: form.git_branch || null,
        release_notes: form.release_notes || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['versions', systemId] })
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
          <DialogTitle>Registrar versión</DialogTitle>
          <DialogDescription>Queda como la versión activa; la anterior pasa a "deprecated".</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="version_number">Versión</Label>
            <Input
              id="version_number"
              required
              placeholder="1.4.2"
              value={form.version_number}
              onChange={(e) => setForm((f) => ({ ...f, version_number: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="git_branch">Rama</Label>
              <Input
                id="git_branch"
                placeholder="main"
                value={form.git_branch ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, git_branch: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="git_commit_hash">Commit</Label>
              <Input
                id="git_commit_hash"
                placeholder="a1b2c3d"
                value={form.git_commit_hash ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, git_commit_hash: e.target.value }))}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="release_notes">Notas de cambios</Label>
            <Textarea
              id="release_notes"
              value={form.release_notes ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, release_notes: e.target.value }))}
            />
          </div>
          {mutation.isError && <ErrorMessage>No se pudo registrar la versión.</ErrorMessage>}
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
