# VPN Bypass

Aplicación GUI para enrutar tráfico específico fuera del túnel VPN (split tunneling). Gestiona dominios, resuelve IPs automáticamente y mantiene rutas de bypass activas mediante un daemon en segundo plano.

---

## Instalación y uso

### 1. Instalar

```bash
python3 main.py
```

**Instalación automática:**
- Dependencias del sistema (`python3-tk`, `python3-yaml`, `dnsutils`, `iproute2`)
- Dispatcher de NetworkManager (`/etc/NetworkManager/dispatcher.d/99-vpn-bypass`)
- Servicio systemd (`vpn-bypass.service`) - se inicia automáticamente al arrancar
- Launcher desktop (`~/.local/share/applications/vpn-bypass.desktop`)

### 2. Uso después de instalar

**Iniciar el daemon (primera vez):**
```bash
sudo systemctl start vpn-bypass.service
```

**Iniciar la GUI:**
```bash
python3 gui.py
# O desde el panel de aplicaciones: "VPN Bypass"
```

**Control del daemon desde la UI:**
- Botón "🔄 Reiniciar Servicio" usa `pkexec` (muestra diálogo gráfico de contraseña)
- La UI detecta automáticamente si usa systemd o modo standalone

### 3. Dependencias verificadas

- `python3-tk` - GUI (instala sin preguntar)
- `python3-yaml` - Módulo Python para configuración
- `dnsutils` - Comando `dig` para DNS
- `iproute2` - Comando `ip` para rutas
- `sudo` - Permisos de administrador

---

## Funcionalidad

| Acción | Descripción |
|--------|-------------|
| **Añadir dominio** | Introduces `google.com` → resuelve IPs → añade rutas de bypass |
| **Monitorear tráfico** | tcpdump cuenta paquetes/bytes por IP |
| **Mantener rutas** | Daemon re-añade rutas si desaparecen |
| **Estadísticas** | UI actualiza cada 5s con datos de tráfico |

### Pestañas

- **Dominios**: Lista con IPs resueltas y estado (activo/inactivo)
- **Rutas**: Tabla de rutas activas con estadísticas

---

## Arquitectura

```
main.py (instalador)
    ↓
SetupManager ───► Instala: tkinter, dependencias, dispatcher, systemd service, launcher
    ↓
vpn_bypass_gui_refactored.py ──► VPNBypassGUI (2 pestañas)
    ↓
VPNManager ──► domains.yml ──► vpn_bypass_daemon (systemd service)
    ↑                                    ↓
    └──────── FileWatcher ←── status.json
```

### Componentes

| Archivo | Función |
|---------|---------|
| `main.py` | **Instalador**. Ejecutar una sola vez. Instala dependencias, dispatcher, servicio systemd, launcher desktop |
| `vpn_bypass_gui_refactored.py` | **Interfaz gráfica**. Ejecutar para iniciar la GUI (tiene `if __name__ == "__main__"`). 2 pestañas, FileWatcher, actualiza tabla |
| `setup_dialog.py` | Diálogo de dependencias (llamado por SetupManager) |
| `setup_manager.py` | Lógica de instalación: apt, permisos, dispatcher, systemd service, launcher |
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
| `~/vpn_bypass_daemon.log` | Logs del daemon | Daemon (root) |
| `/etc/NetworkManager/dispatcher.d/99-vpn-bypass` | Script eventos red | Setup (main.py) |
| `/etc/systemd/system/vpn-bypass.service` | Servicio systemd auto-inicio | Setup (main.py) |
| `~/.local/share/applications/vpn-bypass.desktop` | Launcher panel aplicaciones | Setup (main.py) |

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
  "timestamp": "2024-01-15T10:30:00",
  "routes": [
    {"dest": "142.250.80.46", "gateway": "192.168.1.1", "interface": "eth0"}
  ],
  "stats": {
    "142.250.80.46": {"packets_in": 100, "bytes_in": 50000}
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
