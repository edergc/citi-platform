# Despliegue del Agente CITI en servidores Linux (Oracle Linux)

Guía paso a paso para instalar el Agente CITI en un servidor Linux, desde una
terminal Windows usando PuTTY. El mismo procedimiento aplica a cualquier distro
basada en `systemd` (Oracle Linux, RHEL, CentOS, Rocky, etc.), no solo Oracle Linux.

## Antes de empezar

- El servidor debe estar registrado en CITI Platform con **Sistema operativo: Linux**
  (Servidores → el servidor → Editar). Si lo creaste antes con "Windows" por error,
  corrígelo primero — el botón "Descargar instalador" arma un paquete distinto según
  este campo.
- Necesitas: la IP del servidor, un usuario con acceso SSH, y su contraseña (o llave).
- El usuario debe poder usar `sudo` (o ser `root` directamente) — el agente necesita
  permisos de administrador para poder iniciar/detener/reiniciar otros servicios del
  sistema, igual que corre como `SYSTEM` en los servidores Windows.
- **No necesita salida a internet.** El instalador trae empaquetadas las dependencias
  de Python (`websockets`, `psutil`) para no depender del proxy institucional. Solo si
  la versión de Python de ese servidor es muy distinta a las que se empaquetaron
  (3.8–3.13, x86_64), el instalador intenta bajarlas de PyPI como respaldo.

## Paso 1 — Descargar el instalador

En CITI Platform: **Servidores → (el servidor Linux) → Descargar instalador**.

Se descarga un archivo `citi-agent-NOMBRE.tar.gz` a tu carpeta de Descargas. Cada
descarga genera un token de enrolamiento nuevo (de un solo uso), así que descárgalo
justo antes de instalar — si pasa mucho tiempo o ya lo usaste, vuelve a descargarlo.

## Paso 2 — Copiar el archivo al servidor

Desde PowerShell o CMD, con `pscp` (viene con el instalador completo de PuTTY):

```powershell
pscp "C:\Users\TU_USUARIO\Downloads\citi-agent-NOMBRE.tar.gz" usuario@IP_DEL_SERVIDOR:/tmp/
```

Te pide la contraseña de ese usuario. Si `pscp` no se reconoce como comando, revisa
que esté en la misma carpeta que `putty.exe` (se instala junto si usaste el instalador
`.msi` completo, no el `.exe` suelto).

Alternativa sin instalar nada — Windows 10/11 ya trae `scp` integrado:

```powershell
scp "C:\Users\TU_USUARIO\Downloads\citi-agent-NOMBRE.tar.gz" usuario@IP_DEL_SERVIDOR:/tmp/
```

## Paso 3 — Conectarte por SSH

Con PuTTY como siempre (IP, puerto 22, tu usuario), o directo desde PowerShell:

```powershell
putty.exe -ssh usuario@IP_DEL_SERVIDOR
```

## Paso 4 — Ejecutar el instalador

Ya dentro de la sesión de PuTTY:

```bash
cd /tmp
tar -xzf citi-agent-*.tar.gz
sudo ./install.sh
```

> Si el usuario con el que entraste **ya es root**, quita el `sudo`.

El script hace, en orden:

1. Verifica que el usuario sea root (o tenga sudo).
2. Verifica que `python3` esté disponible.
3. Prueba conectividad de red hacia CITI Core.
4. Copia el agente a `/opt/citi-agent` y crea un entorno virtual de Python ahí.
5. Instala las dependencias — primero intenta con los paquetes incluidos en el
   instalador (sin tocar la red); si no son compatibles con ese Python/arquitectura,
   intenta bajarlas de PyPI como respaldo.
6. Enrola el agente contra CITI Core con el token del paquete.
7. Registra y arranca el servicio `systemd` llamado **`citi-agent`**.
8. Espera unos segundos y confirma que el agente reportó conexión exitosa.

Al final muestra **"Listo. El Agente CITI está corriendo y conectado..."**, o te
explica exactamente qué falló (sin conexión de red, sin Python, dependencias no
instalables, etc.).

## Paso 5 — Confirmar

- En CITI Platform → Servidores → ese servidor debe mostrar **"Agente activo"**, y
  poco después empezar a mostrar métricas (CPU, RAM, disco, red) en su página de
  detalle.
- Desde la misma sesión de PuTTY, para revisar el servicio directamente:

  ```bash
  sudo systemctl status citi-agent
  ```

- Para ver el log en vivo (útil si algo no conecta):

  ```bash
  sudo journalctl -u citi-agent -f
  ```
  (`Ctrl+C` para salir)

## Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `pscp`/`scp` pide contraseña y la rechaza | Usuario o contraseña incorrectos, o la cuenta de SSH es distinta a la que tienes anotada | Confirma la credencial real de acceso SSH a ese servidor (puede no ser la misma que usa el sistema institucional) |
| El instalador falla en "Verificando conectividad de red hacia CITI Core" | El servidor no tiene ruta de red hacia el servidor de CITI Platform, o un firewall bloquea el puerto | Revisa firewall/reglas de red entre ese servidor y CITI Core |
| Falla instalando dependencias, dice "no hay salida a internet/PyPI" | La versión de Python de ese servidor no es ninguna de las empaquetadas (3.8–3.13 x86_64) | Instala manualmente en `/opt/citi-agent/venv` con `pip install websockets psutil`, o instala una versión de Python cubierta (`sudo dnf install python3.11`) y vuelve a correr `install.sh` |
| El servicio no llega a "active" | Revisa el detalle del error | `sudo journalctl -u citi-agent -n 50 --no-pager` |
| El agente corre pero CITI Platform no lo muestra "activo" | Problema de red/firewall entre el agente y CITI Core, o el token de enrolamiento ya expiró/se usó | Genera un instalador nuevo desde CITI Platform (token de un solo uso) y repite desde el Paso 1 |

## Reinstalar o mover el agente

Si necesitas reinstalar (por ejemplo, cambió la IP del servidor de CITI Core), repite
los pasos 1 a 4 completos — `install.sh` detecta si el servicio `citi-agent` ya existe,
lo detiene y lo reconfigura desde cero, sin dejar restos del anterior.

## Diferencias con el agente de Windows (por si migras conocimiento entre ambos)

| | Windows | Linux |
|---|---|---|
| Paquete | `.zip` | `.tar.gz` |
| Instalador | `install.bat` → `install.ps1` | `install.sh` |
| Administrador de servicios | NSSM (Servicio de Windows) | `systemd` |
| Nombre del servicio | `CitiAgent` | `citi-agent` |
| Reiniciar otros servicios | `Start-Service`/`Stop-Service` (PowerShell) | `systemctl start/stop/restart` |
| Eventos críticos | Visor de Sucesos (`wevtutil`) | Journal de systemd (`journalctl`) |
| Python | Incluido en el paquete (portable) | Usa el `python3` del sistema + venv |
| Usuario del servicio | `SYSTEM` (administrador total) | `root` |
