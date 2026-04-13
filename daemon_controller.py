#!/usr/bin/env python3
"""
DaemonController - Gestión independiente del daemon VPN Bypass
Fusionado con vpn_daemon_control_v3.py
"""
import os
import sys
import subprocess
import signal
import time
import logging
from typing import Callable, Optional

try:
    from config import DAEMON_SCRIPT_NAME
except ImportError:
    DAEMON_SCRIPT_NAME = "vpn_bypass_daemon.py"

logger = logging.getLogger(__name__)


# === FUNCIONES DE BAJO NIVEL (antes vpn_daemon_control_v3.py) ===

def _is_daemon_running() -> bool:
    """Verifica si el daemon está corriendo"""
    try:
        result = subprocess.run(
            ['pgrep', '-f', DAEMON_SCRIPT_NAME],
            capture_output=True, text=True
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except:
        return False

def _get_daemon_pids() -> list:
    """Obtiene todos los PIDs del daemon"""
    try:
        result = subprocess.run(
            ['pgrep', '-f', DAEMON_SCRIPT_NAME],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return [int(pid.strip()) for pid in result.stdout.strip().split('\n') if pid.strip()]
        return []
    except:
        return []

def _start_daemon_process() -> bool:
    """Inicia el proceso daemon"""
    try:
        if _is_daemon_running():
            logger.info("[DAEMON] Ya está corriendo")
            return True

        script_dir = os.path.dirname(os.path.abspath(__file__))
        daemon_script = os.path.join(script_dir, DAEMON_SCRIPT_NAME)

        process = subprocess.Popen(
            [sys.executable, daemon_script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        logger.info(f"[DAEMON] Proceso iniciado (PID: {process.pid})")
        return True
    except Exception as e:
        logger.error(f"[DAEMON] Error iniciando proceso: {e}")
        return False

def _stop_daemon_process() -> bool:
    """Detiene el proceso daemon (SIGTERM -> SIGKILL si persiste)"""
    try:
        if not _is_daemon_running():
            return True

        pids = _get_daemon_pids()
        if not pids:
            return True

        logger.info(f"[DAEMON] Deteniendo (PIDs: {pids})")

        # SIGTERM
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass

        time.sleep(2)

        # SIGKILL si persiste
        remaining = _get_daemon_pids()
        if remaining:
            logger.warning(f"[DAEMON] SIGKILL a procesos restantes: {remaining}")
            for pid in remaining:
                try:
                    os.kill(pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
            time.sleep(1)

        return not _is_daemon_running()
    except Exception as e:
        logger.error(f"[DAEMON] Error deteniendo proceso: {e}")
        return False

def _notify_reload_signal() -> bool:
    """Notifica al daemon que recargue configuración (SIGUSR2)"""
    try:
        if not _is_daemon_running():
            logger.warning("[DAEMON] No se puede notificar: daemon no está corriendo")
            return False
        pids = _get_daemon_pids()
        if pids:
            logger.info(f"[DAEMON] Enviando SIGUSR2 al daemon (PID: {pids[0]})")
            os.kill(pids[0], signal.SIGUSR2)
            return True
        logger.warning("[DAEMON] No se encontró PID del daemon")
        return False
    except Exception as e:
        logger.error(f"[DAEMON] Error enviando señal reload: {e}")
        return False


def _is_systemd_service_available() -> bool:
    """Verifica si el servicio systemd está instalado"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-enabled', 'vpn-bypass.service'],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except:
        return False


def _restart_systemd_service() -> bool:
    """Reinicia el servicio systemd usando pkexec (diálogo gráfico de contraseña)"""
    try:
        logger.info("[DAEMON] Reiniciando servicio systemd con pkexec...")

        # Usar pkexec para mostrar diálogo gráfico de autenticación
        result = subprocess.run(
            ['pkexec', 'systemctl', 'restart', 'vpn-bypass.service'],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            logger.info("[DAEMON] Servicio reiniciado correctamente")
            return True
        else:
            logger.error(f"[DAEMON] Error reiniciando servicio: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"[DAEMON] Error en restart systemd: {e}")
        return False


def _stop_systemd_service() -> bool:
    """Detiene el servicio systemd usando pkexec"""
    try:
        result = subprocess.run(
            ['pkexec', 'systemctl', 'stop', 'vpn-bypass.service'],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"[DAEMON] Error deteniendo servicio systemd: {e}")
        return False


def _start_systemd_service() -> bool:
    """Inicia el servicio systemd usando pkexec"""
    try:
        result = subprocess.run(
            ['pkexec', 'systemctl', 'start', 'vpn-bypass.service'],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"[DAEMON] Error iniciando servicio systemd: {e}")
        return False


class DaemonController:
    """Controla el ciclo de vida del daemon VPN Bypass (modo systemd o standalone)"""

    def __init__(self):
        self._status_callbacks: list[Callable[[bool], None]] = []
        self._daemon_process = None
        self._use_systemd = _is_systemd_service_available()
        if self._use_systemd:
            logger.info("[DAEMON] Usando modo systemd (pkexec para privilegios)")

    def is_running(self) -> bool:
        """Verifica si el daemon está corriendo"""
        return _is_daemon_running()

    def restart(self) -> bool:
        """Reinicia el daemon (con diálogo pkexec si es systemd)"""
        try:
            if self._use_systemd:
                result = _restart_systemd_service()
            else:
                # Modo standalone: detener e iniciar
                _stop_daemon_process()
                time.sleep(1)
                result = _start_daemon_process()

            if result:
                logger.info("[DAEMON] Reiniciado correctamente")
                self._notify_status_change(True)
            else:
                logger.error("[DAEMON] Falló al reiniciar")
            return result
        except Exception as e:
            logger.error(f"[DAEMON] Error reiniciando: {e}")
            return False

    def start(self) -> bool:
        """Inicia el daemon (con diálogo pkexec si es systemd)"""
        try:
            if self.is_running():
                logger.info("[DAEMON] Ya está corriendo")
                return True

            if self._use_systemd:
                result = _start_systemd_service()
            else:
                result = _start_daemon_process()

            if result:
                logger.info("[DAEMON] Iniciado correctamente")
                self._notify_status_change(True)
            else:
                logger.error("[DAEMON] Falló al iniciar")
            return result
        except Exception as e:
            logger.error(f"[DAEMON] Error iniciando: {e}")
            return False

    def stop(self) -> bool:
        """Detiene el daemon (con diálogo pkexec si es systemd)"""
        try:
            if not self.is_running():
                logger.info("[DAEMON] No está corriendo")
                return True

            if self._use_systemd:
                result = _stop_systemd_service()
            else:
                result = _stop_daemon_process()

            if result:
                logger.info("[DAEMON] Detenido correctamente")
                self._notify_status_change(False)
            else:
                logger.error("[DAEMON] Falló al detener")
            return result
        except Exception as e:
            logger.error(f"[DAEMON] Error deteniendo: {e}")
            return False

    def uses_systemd(self) -> bool:
        """Retorna True si el daemon está configurado como servicio systemd"""
        return self._use_systemd

    def get_pid(self) -> Optional[int]:
        """Obtiene el PID del daemon si está corriendo"""
        pids = _get_daemon_pids()
        return pids[0] if pids else None

    def get_status(self) -> dict:
        """Obtiene el estado detallado del daemon"""
        try:
            running = _is_daemon_running()
            return {'daemon_running': running, 'message': 'Daemon activo' if running else 'Daemon inactivo'}
        except Exception as e:
            logger.error(f"[DAEMON] Error obteniendo estado: {e}")
            return {"running": False, "error": str(e)}

    def notify_reload(self) -> bool:
        """Notifica al daemon que debe recargar configuración"""
        try:
            result = _notify_reload_signal()
            if result:
                logger.info("[DAEMON] Notificación de reload enviada")
            return result
        except Exception as e:
            logger.error(f"[DAEMON] Error notificando reload: {e}")
            return False

    def register_status_callback(self, callback: Callable[[bool], None]) -> None:
        """Registra callback para cambios de estado"""
        self._status_callbacks.append(callback)

    def unregister_status_callback(self, callback: Callable[[bool], None]) -> None:
        """Desregistra callback"""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)

    def _notify_status_change(self, is_running: bool) -> None:
        """Notifica a todos los callbacks registrados"""
        for callback in self._status_callbacks:
            try:
                callback(is_running)
            except Exception as e:
                logger.error(f"[DAEMON] Error en callback: {e}")
