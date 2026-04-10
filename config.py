"""
Configuración centralizada de rutas de archivos para VPN Bypass
"""
import os

# === Directorio del proyecto ===
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# === Directorios del sistema ===
TEMP_DIR = "/tmp"
SYSTEMD_SERVICE_DIR = "/etc/systemd/system"

# === Archivos de estado (IPC) ===
STATUS_FILE = os.path.join(TEMP_DIR, "vpn_bypass_status.json")  # Unificado: VPN + daemon + rutas
EVENT_FILE = os.path.join(TEMP_DIR, "vpn_bypass_event.json")   # Eventos dispatcher → daemon
ROUTES_FILE = os.path.join(TEMP_DIR, "vpn_bypass_routes.json")  # Rutas aplicadas por el daemon (para cleanup)

# === Archivos de daemon ===
DAEMON_LOG_FILE = os.path.expanduser("~/vpn_bypass_daemon.log")

# === Archivos de configuración (ahora en el proyecto) ===
DOMAINS_FILE = os.path.join(PROJECT_DIR, "domains.yml")

# === Archivos de systemd ===
SERVICE_NAME = "vpn-bypass.service"
SERVICE_TEMPLATE_FILE = os.path.join(PROJECT_DIR, "vpn-bypass.service.template")
SERVICE_DEST_PATH = os.path.join(SYSTEMD_SERVICE_DIR, SERVICE_NAME)

# === Dispatcher de NetworkManager ===
DISPATCHER_DIR = "/etc/NetworkManager/dispatcher.d/"
DISPATCHER_DEST_NAME = "99-vpn-bypass"
DISPATCHER_SRC_NAME = "vpn_dispatcher.py"

# === Nombres de scripts ===
DAEMON_SCRIPT_NAME = "vpn_bypass_daemon.py"

# === Desktop Launcher ===
DESKTOP_APP_NAME = "VPN Bypass"
DESKTOP_COMMENT = "Split tunneling para VPN"
DESKTOP_ICON = "network-vpn"
DESKTOP_CATEGORIES = "Network;System;"
DESKTOP_KEYWORDS = "vpn;bypass;routing;"
DESKTOP_FILE_NAME = "vpn-bypass.desktop"
DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")

