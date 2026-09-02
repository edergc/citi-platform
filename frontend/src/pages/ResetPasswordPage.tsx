import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Scale } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorMessage } from '@/components/ui/error-message'
import { api } from '@/lib/api'

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (newPassword !== confirmPassword) {
      setError('Las contraseñas no coinciden')
      return
    }

    setSubmitting(true)
    try {
      const { data } = await api.post<{ message: string }>('/auth/reset-password', {
        token,
        new_password: newPassword,
      })
      setMessage(data.message)
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'No se pudo restablecer la contraseña.'
      setError(detail)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full border border-amber-500/40 bg-red-950/40">
            <Scale className="h-6 w-6 text-amber-500" />
          </div>
          <p className="text-xs font-medium uppercase tracking-widest text-slate-400">
            Poder Judicial del Perú — Corte Superior de Justicia de Lima
          </p>
          <h1 className="text-xl font-bold text-slate-100">CITI Platform</h1>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Elegir nueva contraseña</CardTitle>
            <CardDescription>Ingresa tu nueva contraseña institucional</CardDescription>
          </CardHeader>
          <CardContent>
            {!token ? (
              <ErrorMessage>El enlace no es válido. Solicita uno nuevo desde la página de restablecimiento.</ErrorMessage>
            ) : message ? (
              <div className="flex flex-col gap-3">
                <p className="text-sm text-emerald-400">{message}</p>
                <Link to="/login">
                  <Button className="w-full">Ir a iniciar sesión</Button>
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="new-password">Nueva contraseña</Label>
                  <Input
                    id="new-password"
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="confirm-password">Confirmar contraseña</Label>
                  <Input
                    id="confirm-password"
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                  />
                </div>
                {error && <ErrorMessage>{error}</ErrorMessage>}
                <Button
                  type="submit"
                  disabled={submitting}
                  className="mt-2 bg-red-800 text-white hover:bg-red-700 focus-visible:ring-amber-500"
                >
                  {submitting ? 'Guardando…' : 'Restablecer contraseña'}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        <div className="mt-6 text-center">
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver al inicio de sesión
          </Link>
        </div>
      </div>
    </div>
  )
}
