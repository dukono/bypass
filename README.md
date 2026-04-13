# VPN Bypass

Aplicación GUI para enrutar tráfico específico fuera del túnel VPN (split tunneling). Gestiona dominios, resuelve IPs automáticamente y mantiene rutas de bypass activas mediante un daemon en segundo plano.

---

## Instalación y uso

### 1. Instalar

**Antes de instalar, actualiza tu sistema:**
```bash
sudo apt update && sudo apt upgrade -y
```

**Ejecutar instalador:**
```bash
sudo python3 main.py
```

**Instalación automática:**
- Dependencias del sistema (`python3-tk`, `python3-yaml`, `dnsutils`, `iproute2`)
- Dispatcher de NetworkManager (`/etc/NetworkManager/dispatcher.d/99-vpn-bypass`)
- Servicio systemd (`vpn-bypass.service`) - se inicia automáticamente al arrancar

### 2. Uso después de instalar

**Iniciar la GUI (y lanzar el daemon desde ella):**
```bash
sudo python3 gui.py
```

**En la UI:**
- Si el daemon está inactivo, usa el botón "▶️ Iniciar" del menú desplegable
- El botón "Reiniciar" del menú principal reinicia el servicio systemd

**Control del daemon desde la UI:**
- Botón estilo GitHub con dropdown: botón principal "Reiniciar", dropdown con "Iniciar", "Detener", "Reiniciar"
- La UI detecta automáticamente si usa systemd o modo standalone
- Muestra PID del daemon en la barra de estado

### 3. Dependencias verificadas

- `python3-tk` - GUI (verificado primero, instala interactivamente si falta)
- `python3-yaml` - Módulo Python para configuración
- `dnsutils` - Comando `dig` para DNS
- `iproute2` - Comando `ip` para rutas
- `sudo` - Permisos de administrador

---

## Funcionalidad

| Acción | Descripción |
|--------|-------------|
| **Añadir dominio** | Introduces dominio → resuelve IPs → añade rutas de bypass vía gateway normal |
| **Mantener rutas** | Daemon re-añade rutas cuando la VPN se activa/desactiva |
| **Estado VPN** | Daemon monitorea interfaz configurada, notifica a UI vía JSON |
| **Control daemon** | Botón GitHub-style para iniciar/detener/reiniciar el servicio |

### Pestañas

- **Dominios**: Lista con IPs resueltas y estado (activo/inactivo)
- **Rutas**: Tabla de rutas activas con información del dominio asociado

### Indicadores de estado

- **Daemon**: Muestra si está activo/inactivo con PID
- **VPN**: Muestra "Activa/Inactiva/Desconocido" según el estado reportado por el daemon

---

## Arquitectura

```
main.py (instalador)
    ↓
SetupDialog (modo auto) ───► Instala: tkinter, dnsutils, iproute2
    ↓
SetupManager ───► Instala: dispatcher, systemd service
    ↓
gui.py ──► VPNBypassGUI (pestañas Dominios y Rutas, indicador VPN/Daemon)
    ↓
VPNManager ──► domains.yml ──► vpn_bypass_daemon (systemd service)
    ↑                                    ↓
    └──────── FileWatcher ←── /tmp/vpn_bypass_status.json (vpn_active + domain_ips)
```

### Componentes

| Archivo | Función |
|---------|---------|
| `main.py` | **Instalador**. Ejecutar una sola vez. Instala dependencias, dispatcher, servicio systemd |
| `gui.py` | **Interfaz gráfica**. Ejecutar con `sudo python3 gui.py`. Control del daemon, gestión de dominios |
| `setup_dialog.py` | Diálogo de dependencias con modo automático (instalación sin interacción) |
| `setup_manager.py` | Lógica de instalación: dispatcher, systemd service |
| `vpn_manager.py` | Core: DNS, rutas (ip route), tcpdump stats |
| `vpn_bypass_daemon.py` | Proceso background (gestionado por systemd). Mantiene rutas, escucha domains.yml |
| `daemon_controller.py` | Controla daemon: start/stop/status (pgrep + señales) |
| `file_watcher.py` | Observa status.json, notifica a GUI |
| `traffic_monitor.py` | Timer 5s para refrescar UI |
| `config.py` | Rutas y constantes. `PROJECT_DIR` apunta al directorio del proyecto |
| `vpn_dispatcher.py` | Script NM dispatcher (eventos VPN). Instalado en `/etc/NetworkManager/dispatcher.d/` |
| `vpn-bypass.service.template` | Template para generar el servicio systemd con rutas dinámicas |

---

## Comunicación entre procesos

```
[Usuario] ──► [GUI] ──► domains.yml ──► [Daemon] ──► ip route add
                            ▲                  │
                            │                  ▼
                     [FileWatcher] ◄─── status.json
                            │
                            ▼
                         [GUI actualiza]
```

1. **GUI escribe** `domains.yml` (usuario añade dominio)
2. **Daemon detecta** cambio (polling cada 2s) → ejecuta `ip route add`
3. **Daemon escribe** `status.json` (rutas activas + stats)
4. **FileWatcher** detecta cambio → notifica a GUI
5. **GUI lee** `status.json` → actualiza tabla de rutas

---

## Ficheros del sistema

| Ruta | Propósito | Quién escribe |
|------|-----------|---------------|
| `{PROJECT_DIR}/domains.yml` | Lista de dominios y configuración | GUI (usuario) |
| `/tmp/vpn_bypass_status.json` | Rutas activas y stats | Daemon (root) |
| `/root/vpn_bypass_daemon.log` | Logs del daemon (modo debug) | Daemon (root) |
| `/etc/NetworkManager/dispatcher.d/99-vpn-bypass` | Script eventos red | Setup (main.py) |
| `/etc/systemd/system/vpn-bypass.service` | Servicio systemd auto-inicio | Setup (main.py) |

### Por qué necesita sudo

| Operación | Motivo |
|-----------|--------|
| `ip route add/del` | Tabla de enrutamiento del kernel |
| `/etc/systemd/system/` | Instalar servicio systemd |
| `/etc/NetworkManager/dispatcher.d/` | Dispatcher de red |
| `tcpdump -i interfaz` | Raw sockets para captura |
| `apt install` | Instalar paquetes del sistema |

---

## Formato de datos

### domains.yml
```yaml
domains:
  soundcloud.com:
    status: activo
  qwen.ai:
    status: activo

config:
  vpn_interface: gpd0
  vpn_interfaces:
    - gpd0
    - tun0
    - tun1
    - wg0
    - utun0
    - ppp0
```

### status.json
```json
{
  "vpn_active": true,
  "domain_ips": {
    "chat.qwen.ai": ["47.91.78.155", "47.254.175.31"]
  }
}
```

---

## Troubleshooting

```bash
# Verificar tkinter
python3 -c "import tkinter; print('OK')"

# Verificar daemon corriendo
sudo pgrep -f vpn_bypass_daemon

# Verificar dig instalado
which dig
```
