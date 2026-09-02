import { useState } from 'react'
import { KeyRound, Mail, Phone, Shield, Building2, IdCard } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ChangePasswordDialog } from '@/components/ChangePasswordDialog'

function initials(fullName: string): string {
  return fullName
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')
}

export function ProfilePage() {
  const { user } = useAuth()
  const [changingPassword, setChangingPassword] = useState(false)

  if (!user) return null

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h2 className="text-base font-medium text-slate-200">Mi perfil</h2>
        <p className="text-sm text-slate-500">Información de tu cuenta en CITI Platform.</p>
      </div>

      <Card>
        <CardHeader className="flex-row items-center gap-4 space-y-0">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-red-900/60 text-lg font-semibold text-amber-400">
            {initials(user.full_name)}
          </div>
          <div>
            <CardTitle>{user.full_name}</CardTitle>
            <CardDescription className="flex items-center gap-2">
              {user.username}
              {user.is_superuser && <Badge variant="info">Administrador</Badge>}
              {user.role_name && !user.is_superuser && <Badge variant="default">{user.role_name}</Badge>}
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 border-t border-slate-800 pt-4">
          <div className="flex items-center gap-3 text-sm">
            <IdCard className="h-4 w-4 text-slate-500" />
            <span className="text-slate-400">DNI</span>
            <span className="ml-auto text-slate-200">{user.dni}</span>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <Mail className="h-4 w-4 text-slate-500" />
            <span className="text-slate-400">Correo</span>
            <span className="ml-auto text-slate-200">
              {user.email ?? <span className="italic text-slate-500">Sin correo — pídele a un administrador que lo complete</span>}
            </span>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <Phone className="h-4 w-4 text-slate-500" />
            <span className="text-slate-400">Teléfono</span>
            <span className="ml-auto text-slate-200">{user.phone ?? '—'}</span>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <Building2 className="h-4 w-4 text-slate-500" />
            <span className="text-slate-400">{user.site_names.length > 1 ? 'Sedes' : 'Sede'}</span>
            <span className="ml-auto text-slate-200">{user.site_names.length > 0 ? user.site_names.join(', ') : '—'}</span>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <Shield className="h-4 w-4 text-slate-500" />
            <span className="text-slate-400">Perfil</span>
            <span className="ml-auto text-slate-200">{user.is_superuser ? 'Administrador' : user.role_name ?? '—'}</span>
          </div>
          {user.last_login_at && (
            <p className="pt-2 text-xs text-slate-500">
              Último acceso: {new Date(user.last_login_at).toLocaleString('es-PE')}
            </p>
          )}
        </CardContent>
      </Card>

      <div className="mt-6">
        <Button variant="outline" onClick={() => setChangingPassword(true)}>
          <KeyRound className="h-4 w-4" />
          Cambiar contraseña
        </Button>
      </div>

      <ChangePasswordDialog open={changingPassword} onOpenChange={setChangingPassword} />
    </div>
  )
}
