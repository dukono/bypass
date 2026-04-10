#!/usr/bin/env python3
"""
NetworkManager Dispatcher Script para VPN Bypass
Se ejecuta cuando hay eventos de interfaz y notifica al daemon via señal + JSON
"""
import sys
import os
import subprocess
import json
from datetime import datetime

# Importar rutas desde config.py si está disponible
try:
    from config import EVENT_FILE
except ImportError:
    # Fallback si config.py no está accesible
    EVENT_FILE = "/tmp/vpn_bypass_event.json"

LOG_FILE = "/var/log/vpn_bypass_dispatcher.log"

def log(mensaje):
    """Escribe en el log con timestamp"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a") as f:
            f.write(f"[{timestamp}] {mensaje}\n")
    except:
        pass

def get_daemon_pid():
    """Busca el PID del daemon por nombre de proceso"""
    try:
        # Buscar proceso que contenga 'vpn_bypass_daemon.py' en su línea de comando
        result = subprocess.run(['pgrep', '-f', 'vpn_bypass_daemon.py'],
                              capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            # Filtrar solo procesos python3 (no el script de sudo ni pydevd)
            for pid_str in pids:
                if not pid_str:
                    continue
                try:
                    pid = int(pid_str)
                    # Verificar que sea un proceso python real
                    cmdline = subprocess.run(['cat', f'/proc/{pid}/cmdline'],
                                         capture_output=True, text=True)
                    if 'python' in cmdline.stdout.lower():
                        return pid
                except:
                    continue
    except Exception as e:
        log(f"Error buscando daemon: {e}")
    return None

def is_daemon_running():
    """Verifica si el daemon está corriendo"""
    pid = get_daemon_pid()
    if pid:
        try:
            os.kill(pid, 0)
            return True
        except:
            pass
    return False

def notify_daemon(interface, action):
    """Notifica al daemon usando señal + JSON"""
    try:
        # Verificar si el daemon está corriendo
        if not is_daemon_running():
            log("Daemon no está corriendo, no se puede notificar")
            return False

        # Crear archivo de evento para el daemon
        event_file = EVENT_FILE
        event_data = {
            'interface': interface,
            'action': action,
            'timestamp': subprocess.run(['date', '+%s'], capture_output=True, text=True).stdout.strip()
        }

        with open(event_file, 'w') as f:
            json.dump(event_data, f)

        # Enviar señal SIGUSR1 al daemon (buscando por nombre)
        pid = get_daemon_pid()
        if not pid:
            log("No se encontró PID del daemon")
            return False
        os.kill(pid, 10)  # SIGUSR1

        log(f"Notificado daemon: {interface} {action}")
        return True

    except Exception as e:
        log(f"Error notificando daemon: {str(e)}")
        return False

# --- LÓGICA PRINCIPAL ---
# NetworkManager pasa la interfaz como $1 y la acción como $2
log(f"NetworkManager Event: {sys.argv}")

if len(sys.argv) < 3:
    log("Argumentos insuficientes")
    sys.exit(0)

interface = sys.argv[1]
action = sys.argv[2]

# Reenviar todos los eventos al daemon - el daemon verificará si la interfaz está configurada
log(f"Reenviando evento al daemon: {interface} {action}")

if action in ['up', 'down']:
    if notify_daemon(interface, action):
        log(f"Daemon notificado: {interface} {action}")
    else:
        log(f"No se pudo notificar al daemon: {interface} {action}")
else:
    log(f"Acción {action} no manejada para {interface}")

sys.exit(0)
