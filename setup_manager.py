#!/usr/bin/env python3
"""
SetupManager - Gestiona la instalación de dependencias y configuración del sistema
"""
import os
import sys
import subprocess
import logging
from config import (DISPATCHER_DIR, DISPATCHER_DEST_NAME, DISPATCHER_SRC_NAME,
                    PROJECT_DIR, SERVICE_NAME, SERVICE_TEMPLATE_FILE, SERVICE_DEST_PATH,
                    DAEMON_SCRIPT_NAME, TEMP_DIR)

logger = logging.getLogger(__name__)


class SetupManager:
    """Gestiona la instalación de dependencias y configuración del sistema"""

    def __init__(self, script_dir: str = None):
        self.script_dir = script_dir or os.path.dirname(os.path.abspath(__file__))
        self.logger = logging.getLogger(self.__class__.__name__)

    def run_all_checks(self) -> bool:
        """Ejecuta todas las verificaciones e instalaciones necesarias"""
        self.logger.info("[INIT] Iniciando verificación de dependencias...")

        if not self.check_and_install_tk():
            return False

        self.logger.info("[INIT] Verificando dependencias del sistema...")
        if not self.check_and_install_system_deps():
            return False

        self.logger.info("[INIT] Verificando dispatcher de NetworkManager...")
        if not self.check_and_install_dispatcher():
            return False

        self.logger.info("[INIT] Configurando servicio systemd...")
        if not self.check_and_install_systemd_service():
            return False

        self.logger.info("[INIT] Todas las dependencias verificadas correctamente")
        return True

    def check_and_install_tk(self) -> bool:
        """Verifica e instala python3-tk si es necesario"""
        try:
            import tkinter
            return True
        except ImportError:
            self.logger.info("[SETUP] Instalando python3-tk automáticamente...")
            try:
                result = subprocess.run(['sudo', 'apt', 'install', '-y', 'python3-tk'],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    self.logger.info("[SETUP] python3-tk instalado correctamente")
                    return True

                self.logger.info("[SETUP] Actualizando repositorios...")
                subprocess.run(['sudo', 'apt', 'update'], check=True, capture_output=True)
                subprocess.run(['sudo', 'apt', 'install', '-y', 'python3-tk'], check=True, capture_output=True)
                self.logger.info("[SETUP] python3-tk instalado correctamente")
                return True

            except subprocess.CalledProcessError as e:
                self.logger.error(f"[SETUP] Error instalando python3-tk: {e}")
                self.logger.info("\n[SETUP] Opciones alternativas:")
                self.logger.info("[SETUP] 1. Ejecutar manualmente: sudo apt install python3-tk")
                self.logger.info("[SETUP] 2. Usar el gestor simple: python3 vpn_manager_simple.py")
                self.logger.info("[SETUP] 3. Instalar tkinter con pip: pip install tk")
                return False
            except Exception as e:
                self.logger.error(f"[SETUP] Error inesperado: {e}")
                return False

    def check_and_install_system_deps(self) -> bool:
        """Verifica e instala dependencias del sistema (dig, iproute2)"""
        deps_needed = []

        # Verificar dig (dnsutils)
        try:
            subprocess.run(['dig', '-v'], capture_output=True, check=True)
        except:
            deps_needed.append('dnsutils')

        # Verificar ip route (iproute2)
        try:
            subprocess.run(['ip', 'route'], capture_output=True, check=True)
        except:
            deps_needed.append('iproute2')

        if deps_needed:
            self.logger.info(f"[SETUP] Instalando dependencias del sistema: {', '.join(deps_needed)}...")
            try:
                subprocess.run(['sudo', 'apt', 'update'], check=True, capture_output=True)
                subprocess.run(['sudo', 'apt', 'install', '-y'] + deps_needed, check=True, capture_output=True)
                self.logger.info(f"[SETUP] Dependencias instaladas: {', '.join(deps_needed)}")
                return True
            except Exception as e:
                self.logger.error(f"[SETUP] Error instalando dependencias: {e}")
                return False
        return True

    def check_and_install_dispatcher(self) -> bool:
        """Verifica e instala el dispatcher de NetworkManager (siempre sobrescribe)"""
        dispatcher_dir = DISPATCHER_DIR
        dispatcher_dest = os.path.join(dispatcher_dir, DISPATCHER_DEST_NAME)
        dispatcher_src = os.path.join(self.script_dir, DISPATCHER_SRC_NAME)

        # Instalar/copiar el dispatcher (siempre sobrescribe)
        self.logger.info(f"[SETUP] Instalando dispatcher en {dispatcher_dest}...")
        try:
            # Verificar que el directorio existe
            if not os.path.exists(dispatcher_dir):
                self.logger.error(f"[SETUP] Error: Directorio {dispatcher_dir} no existe")
                return False

            # Copiar archivo
            subprocess.run(['sudo', 'cp', dispatcher_src, dispatcher_dest], check=True)

            # Hacer ejecutable
            subprocess.run(['sudo', 'chmod', '+x', dispatcher_dest], check=True)

            self.logger.info(f"[SETUP] Dispatcher instalado correctamente en {dispatcher_dest}")

            # Recargar NetworkManager para aplicar cambios
            try:
                subprocess.run(['sudo', 'systemctl', 'reload', 'NetworkManager'], check=True, capture_output=True)
                self.logger.info("[SETUP] NetworkManager recargado")
            except:
                self.logger.info("[SETUP] Nota: No se pudo recargar NetworkManager automáticamente")

            return True
        except Exception as e:
            self.logger.error(f"[SETUP] Error instalando dispatcher: {e}")
            return False

    def check_and_install_systemd_service(self) -> bool:
        """Verifica e instala el servicio systemd para auto-inicio"""
        self.logger.info("[SETUP] Configurando servicio systemd...")

        # Verificar si systemd está disponible
        if not os.path.exists("/etc/systemd/system"):
            self.logger.warning("[SETUP] systemd no parece estar disponible en este sistema")
            return True  # No es un error fatal

        # Generar contenido del servicio desde template
        try:
            with open(SERVICE_TEMPLATE_FILE, 'r') as f:
                template_content = f.read()

            service_content = template_content.format(PROJECT_DIR=PROJECT_DIR)

            # Instalar el servicio (siempre sobrescribe)
            self.logger.info(f"[SETUP] Instalando servicio systemd en {SERVICE_DEST_PATH}...")

            # Crear archivo temporal y copiar con sudo
            temp_service = os.path.join(TEMP_DIR, SERVICE_NAME)
            with open(temp_service, 'w') as f:
                f.write(service_content)

            subprocess.run(['sudo', 'cp', temp_service, SERVICE_DEST_PATH], check=True)
            os.remove(temp_service)

            # Recargar systemd
            subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True, capture_output=True)

            # Habilitar el servicio (inicio automático)
            subprocess.run(['sudo', 'systemctl', 'enable', SERVICE_NAME], check=True, capture_output=True)

            self.logger.info("[SETUP] Servicio systemd instalado y habilitado")
            self.logger.info(f"[SETUP] Usar: sudo systemctl start {SERVICE_NAME}")

            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"[SETUP] Error instalando servicio systemd: {e}")
            return False
        except Exception as e:
            self.logger.error(f"[SETUP] Error inesperado: {e}")
            return False

