/** Human-readable Spanish labels for the audit trail — keeps the "Auditoría" tab
 * understandable for non-technical staff instead of showing raw action/entity codes. */

export const ACTION_LABELS: Record<string, string> = {
  'agent.enroll_token_created': 'Token de enrolamiento de Agente generado',
  'agent.installer_downloaded': 'Instalador del Agente descargado',
  'alert_event.acknowledged': 'Alerta reconocida',
  'alert_rule.created': 'Regla de alerta creada',
  'alert_rule.deleted': 'Regla de alerta eliminada',
  'alert_rule.updated': 'Regla de alerta modificada',
  'auth.login': 'Inicio de sesión',
  'auth.login_failed': 'Intento de inicio de sesión fallido',
  'auth.password_changed': 'Cambio de contraseña',
  'auth.password_reset_completed': 'Restablecimiento de contraseña completado',
  'auth.password_reset_requested': 'Solicitud de restablecimiento de contraseña',
  'backup.triggered': 'Respaldo ejecutado',
  'backup_job.created': 'Job de respaldo creado',
  'backup_job.deleted': 'Job de respaldo eliminado',
  'backup_job.updated': 'Job de respaldo modificado',
  'config.created': 'Variable de configuración creada',
  'config.deleted': 'Variable de configuración eliminada',
  'config.updated': 'Variable de configuración modificada',
  'dependency.created': 'Dependencia registrada',
  'dependency.deleted': 'Dependencia eliminada',
  'deployment.rollback_triggered': 'Rollback de despliegue ejecutado',
  'deployment.triggered': 'Despliegue ejecutado',
  'document.deleted': 'Documento eliminado',
  'document.uploaded': 'Documento subido',
  'license.created': 'Licencia registrada',
  'license.deleted': 'Licencia eliminada',
  'license.updated': 'Licencia modificada',
  'maintenance_window.cancelled': 'Ventana de mantenimiento cancelada',
  'maintenance_window.created': 'Ventana de mantenimiento programada',
  'maintenance_window.updated': 'Ventana de mantenimiento modificada',
  'notification.suppressed_maintenance': 'Notificación suprimida por mantenimiento',
  'notification_channel.created': 'Canal de notificación creado',
  'notification_channel.deleted': 'Canal de notificación eliminado',
  'notification_channel.test_sent': 'Prueba de notificación enviada',
  'notification_channel.updated': 'Canal de notificación modificado',
  'notification_channel.weekly_report_triggered': 'Reporte semanal enviado',
  'platform_secret.updated': 'Secreto de plataforma actualizado',
  'restore.triggered': 'Restauración ejecutada',
  'role.created': 'Perfil creado',
  'role.deleted': 'Perfil eliminado',
  'role.updated': 'Perfil modificado',
  'server.created': 'Servidor creado',
  'server.deleted': 'Servidor eliminado',
  'server.updated': 'Servidor modificado',
  'service.action_triggered': 'Acción de servicio ejecutada',
  'service.created': 'Servicio creado',
  'service.deleted': 'Servicio eliminado',
  'service.updated': 'Servicio modificado',
  'site.created': 'Sede creada',
  'site.deleted': 'Sede eliminada',
  'site.updated': 'Sede modificada',
  'system.created': 'Sistema creado',
  'system.deleted': 'Sistema eliminado',
  'system.updated': 'Sistema modificado',
  'user.created': 'Usuario creado',
  'user.deleted': 'Usuario eliminado',
  'user.password_reset_by_admin': 'Contraseña restablecida por administrador',
  'user.updated': 'Usuario modificado',
  'version.created': 'Versión registrada',
  'version.rollback_triggered': 'Rollback de versión ejecutado',
}

export const ENTITY_LABELS: Record<string, string> = {
  user: 'Usuario',
  alert_rule: 'Regla de alerta',
  alert_event: 'Alerta',
  role: 'Perfil',
  site: 'Sede',
  system: 'Sistema',
  server: 'Servidor',
  service: 'Servicio',
  backup_job: 'Job de respaldo',
  backup_run: 'Respaldo',
  restore_operation: 'Restauración',
  config_entry: 'Variable de configuración',
  system_version: 'Versión',
  deployment: 'Despliegue',
  document: 'Documento',
  license: 'Licencia',
  dependency: 'Dependencia',
  notification_channel: 'Canal de notificación',
  platform_secret: 'Secreto de plataforma',
  maintenance_window: 'Ventana de mantenimiento',
}

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action.replaceAll('.', ' ').replaceAll('_', ' ')
}

export function entityLabel(entityType: string): string {
  return ENTITY_LABELS[entityType] ?? entityType.replaceAll('_', ' ')
}

/** Spanish labels for field names that appear inside a details dict (raw or in changed_fields). */
const FIELD_LABELS: Record<string, string> = {
  dni: 'DNI',
  username: 'usuario',
  full_name: 'nombre completo',
  email: 'correo',
  phone: 'teléfono',
  is_superuser: 'administrador',
  is_active: 'estado activo',
  site_id: 'sede',
  role_id: 'perfil',
  name: 'nombre',
  description: 'descripción',
  criticality: 'criticidad',
  status: 'estado',
  category: 'categoría',
  repo_url: 'repositorio',
  default_branch: 'rama',
  repo_local_path: 'ruta del repositorio',
  deploy_build_command: 'comando de build',
  hostname: 'servidor',
  ip_address: 'dirección IP',
  os_version: 'versión de SO',
  cpu_cores: 'núcleos CPU',
  ram_mb: 'RAM',
  disk_gb: 'disco',
  control_identifier: 'identificador de control',
  port: 'puerto',
  health_check_url: 'URL de verificación',
  server_id: 'servidor',
  service_id: 'servicio',
  service_name: 'servicio',
  system_id: 'sistema',
  type: 'tipo',
  source_path: 'ruta origen',
  storage_path: 'ruta de almacenamiento',
  retention_days: 'días de retención',
  enabled: 'habilitado',
  config: 'configuración',
  value: 'valor',
  is_secret: 'secreto',
  key: 'clave',
  code: 'código',
  address: 'dirección',
  timezone: 'zona horaria',
  permission_codes: 'privilegios',
  changed_fields: 'campos modificados',
  title: 'título',
  doc_type: 'tipo de documento',
  backup_job_id: 'job de respaldo',
  backup_run_id: 'respaldo',
  target_service_id: 'servicio destino',
  target_version_id: 'versión destino',
  version_number: 'versión',
  action: 'acción',
  to: 'destino',
  success: 'enviado',
  regla: 'regla de alerta',
  servidor: 'servidor',
  severidad: 'severidad',
  valor: 'valor',
  razon: 'razón',
  usuario_afectado: 'usuario afectado',
  dni_afectado: 'DNI afectado',
  value_changed: 'valor cambiado',
  metric: 'métrica',
  metric_target: 'objetivo de la métrica',
  condition: 'condición',
  threshold: 'umbral',
  cooldown_minutes: 'minutos de espera entre alertas',
  scope_type: 'alcance',
  scope_id: 'alcance específico',
  site_ids: 'sedes',
  alcance: 'alcance',
  motivo: 'motivo',
  titulo: 'título',
  servidor_id: 'servidor',
}

const ACTION_VALUE_LABELS: Record<string, string> = {
  start: 'iniciar',
  stop: 'detener',
  restart: 'reiniciar',
  force_restart: 'forzar reinicio',
}

function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key.replaceAll('_', ' ')
}

function formatValue(key: string, value: unknown): string {
  if (typeof value === 'boolean') return value ? 'sí' : 'no'
  if (value === null || value === undefined || value === '') return '—'
  if (key === 'action' && typeof value === 'string') return ACTION_VALUE_LABELS[value] ?? value
  if (Array.isArray(value)) {
    return key === 'changed_fields' ? value.map((v) => fieldLabel(String(v))).join(', ') : value.join(', ')
  }
  return String(value)
}

type ChangePair = { antes?: unknown; despues?: unknown }

function isChangePair(value: unknown): value is ChangePair {
  return typeof value === 'object' && value !== null && !Array.isArray(value) && ('antes' in value || 'despues' in value)
}

/** Renders the {campo: {antes, despues}} shape produced by the backend's
 * diff_changed_fields() as "campo: antes → después" pairs — the actual values that
 * changed, not just which fields were touched. */
function formatChanges(changes: Record<string, unknown>): string {
  return Object.entries(changes)
    .filter(([, pair]) => isChangePair(pair))
    .map(([field, pair]) => {
      const { antes, despues } = pair as ChangePair
      return `${fieldLabel(field)}: ${formatValue(field, antes)} → ${formatValue(field, despues)}`
    })
    .join(' · ')
}

/** Renders a details dict as a short, readable Spanish phrase instead of raw JSON.
 * Understands the current "changes" (antes/después) shape and falls back to the
 * older flat "changed_fields" shape for historic rows that predate it. */
export function formatDetails(details: Record<string, unknown> | null): string {
  if (!details || Object.keys(details).length === 0) return '—'
  const parts: string[] = []
  for (const [key, value] of Object.entries(details)) {
    if (key === 'changes' && value && typeof value === 'object' && !Array.isArray(value)) {
      const changesText = formatChanges(value as Record<string, unknown>)
      if (changesText) parts.push(changesText)
      continue
    }
    parts.push(`${fieldLabel(key)}: ${formatValue(key, value)}`)
  }
  return parts.length > 0 ? parts.join(' · ') : '—'
}
