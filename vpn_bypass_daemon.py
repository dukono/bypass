#!/usr/bin/env python3
"""
VPN Bypass Daemon - Versión con señales y archivos JSON (sin D-Bus)
"""
import os
import sys
import time
import signal
import logging
import threading
import subprocess
import json
from vpn_manager import VPNManager, create_manager, check_dependencies
from config import DAEMON_LOG_FILE, EVENT_FILE, STATUS_FILE, ROUTES_FILE, DAEMON_SCRIPT_NAME

# Configuración de logging (por defecto INFO, DEBUG con --debug)
log_file = DAEMON_LOG_FILE
logger = None  # Se inicializa en main() después de verificar --debug

def setup_logging(debug=False):
    """Configura el logging con nivel INFO por defecto, DEBUG con flag"""
    level = logging.DEBUG if debug else logging.INFO

    # Borrar log anterior SOLO en modo debug (para tener log limpio por ejecución)
    if debug and os.path.exists(log_file):
        try:
            os.remove(log_file)
        except Exception:
            pass

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

class VPNDaemon:
    """Daemon para gestión automática de rutas VPN con D-Bus unificado"""
    
    def __init__(self, script_dir):
        self.script_dir = script_dir
        self.manager = None
        self.running = False
        
        # Configurar manejadores de señales
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGUSR1, self.networkmanager_handler)
        signal.signal(signal.SIGUSR2, self.domains_reload_handler)
        
        try:
            self.manager = create_manager(self.script_dir)
            logger.info("VPN Manager inicializado correctamente")
        except Exception as e:
            logger.error(f"No se pudo inicializar VPN Manager: {e}")
            sys.exit(1)
    
    def signal_handler(self, signum, frame):
        """Manejador de señales para cierre graceful"""
        logger.info(f"Recibida señal {signum}, deteniendo daemon...")
        # Limpiar rutas de bypass al detener el daemon
        self.clear_bypass_routes()
        # Limpiar IPs en UI y marcar VPN inactiva
        self.write_status_file(vpn_active=False, domain_ips_map={})
        self.running = False
    
    def networkmanager_handler(self, signum, frame):
        """Manejador de eventos de NetworkManager (SIGUSR1)"""
        try:
            logger.info("Evento de NetworkManager recibido via señal")
            # Leer evento del archivo JSON
            event_file = EVENT_FILE
            if os.path.exists(event_file):
                with open(event_file, 'r') as f:
                    event_data = json.load(f)
                logger.debug(f"[DISPATCHER] Evento JSON recibido: {json.dumps(event_data, indent=2)}")
                interface = event_data.get('interface')
                action = event_data.get('action')
                timestamp = event_data.get('timestamp')
                logger.info(f"[DISPATCHER] Procesando evento: interfaz={interface}, accion={action}, timestamp={timestamp}")
                self.handle_dispatcher_event(interface, action)
            else:
                logger.warning("[DISPATCHER] Archivo de evento no encontrado")
        except Exception as e:
            logger.error(f"Error procesando evento NetworkManager: {e}")
    
    def handle_dispatcher_event(self, interface, action):
        """Maneja eventos del dispatcher (NetworkManager -> Dispatcher -> Daemon)"""
        try:
            logger.info(f"[DISPATCHER] Evento recibido: interface={interface}, action={action}")

            # Obtener la interfaz VPN configurada en la UI
            configured_interface = None
            if self.manager:
                configured_interface = self.manager.get_vpn_interface()
                vpn_interfaces = self.manager.get_vpn_interfaces_list()
                logger.debug(f"[CONFIG] Interfaz configurada: {configured_interface}")
                logger.debug(f"[CONFIG] Interfaces VPN conocidas: {vpn_interfaces}")

            # Verificar si la interfaz recibida coincide con la configurada
            if configured_interface and interface == configured_interface:
                logger.info(f"[DISPATCHER] Interfaz {interface} coincide con configurada, procesando {action}")

                if action == 'up':
                    self.handle_vpn_up(interface)
                elif action == 'down':
                    self.handle_vpn_down(interface)
            else:
                logger.info(f"[DISPATCHER] Interfaz {interface} no coincide con configurada {configured_interface}, ignorando")
                
        except Exception as e:
            logger.error(f"Error procesando evento del dispatcher: {e}")
    
    def send_initial_vpn_status(self):
        """Envía el estado inicial de VPN a la UI cuando el daemon inicia"""
        try:
            # Obtener la interfaz VPN configurada en la UI
            configured_interface = None
            if self.manager:
                configured_interface = self.manager.get_vpn_interface()

            logger.info(f"[INIT] Enviando estado inicial VPN. Interfaz configurada: {configured_interface}")
            
            # Verificar si la interfaz configurada está activa actualmente
            if configured_interface:
                # Verificar si la interfaz está activa (usando flags UP o presencia de IP)
                result = subprocess.run(['ip', 'link', 'show', configured_interface],
                                      capture_output=True, text=True)
                # Interfaces VPN muestran "state UNKNOWN" aunque estén activas
                # La forma fiable: verificar flag LOWER_UP o UP
                is_active = False
                if result.returncode == 0:
                    output = result.stdout
                    # Buscar LOWER_UP en los flags de la interfaz
                    is_active = 'LOWER_UP' in output or 'UP' in output
                
                if is_active:
                    logger.info(f"Interfaz {configured_interface} está activa, aplicando rutas de bypass...")
                    # Aplicar rutas y notificar si cambiaron
                    routes_added, domain_ips_map = self._apply_bypass_routes(configured_interface)
                    if routes_added > 0:
                        # Notificar VPN activa + dominios con IPs
                        self.write_status_file(vpn_active=True, domain_ips_map=domain_ips_map)
                    else:
                        # Notificar VPN activa (sin rutas nuevas)
                        self.write_status_file(vpn_active=True)
                else:
                    logger.info(f"Interfaz {configured_interface} no está activa, notificando a UI")
                    self.write_status_file(vpn_active=False)
            else:
                logger.info("No hay interfaz VPN configurada, notificando estado inactivo a UI")
                self.write_status_file(vpn_active=False)

        except Exception as e:
            logger.error(f"Error enviando estado inicial VPN: {e}")
    
    def domains_reload_handler(self, signum, frame):
        """Manejador de recarga de dominios"""
        try:
            logger.info("Recarga de dominios solicitada")
            self.reload_domains_and_routes()
        except Exception as e:
            logger.error(f"Error recargando dominios: {e}")
    
    def write_status_file(self, vpn_active: bool = None, domain_ips_map: dict = None):
        """Escribe el estado en archivo JSON (solo vpn_active y domain_ips)"""
        try:
            status_file = STATUS_FILE
            data = {}

            # Solo guardar campos que la UI necesita
            if vpn_active is not None:
                data['vpn_active'] = vpn_active
            if domain_ips_map is not None:
                data['domain_ips'] = domain_ips_map

            with open(status_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"[JSON_STATUS] Estado escrito: VPN={'activa' if vpn_active else 'N/A'}")
            logger.debug(f"[JSON_STATUS] Contenido: {json.dumps(data, indent=2)}")
        except Exception as e:
            logger.error(f"[JSON_STATUS] Error escribiendo archivo: {e}")
    
    def _apply_bypass_routes(self, interface: str) -> int:
        """
        Aplica rutas de bypass para dominios activos.
        Retorna número de rutas añadidas.
        """
        try:
            # Obtener gateway e interfaz local via manager
            gateway, local_iface = self.manager.get_local_gateway_and_iface(exclude_interface=interface)

            if not gateway or not local_iface:
                logger.error("[ROUTES] No se pudo detectar gateway o interfaz local")
                return 0

            logger.info(f"[ROUTES] Usando gateway {gateway} via {local_iface}")

            # Cargar dominios y mostrar configuración
            all_domains = self.manager.load_domains()
            domains_with_status = self.manager.get_all_domains_with_status()
            logger.debug(f"[DOMAINS_YML] Dominios cargados desde domains.yml: {all_domains}")
            logger.debug(f"[DOMAINS_YML] Dominios con estado: {domains_with_status}")

            # Cargar rutas previamente aplicadas para acumular
            existing_routes = self._load_applied_routes()
            applied_routes_set = set(existing_routes)
            logger.debug(f"[ROUTES] Rutas existentes cargadas: {existing_routes}")

            # Aplicar rutas solo para dominios activos
            active_domains = self.manager.get_active_domains()
            routes_added = 0

            logger.info(f"[ROUTES] Procesando {len(active_domains)} dominios activos de {len(all_domains)} totales")
            logger.debug(f"[ROUTES] Lista de dominios activos: {active_domains}")

            # Mapeo dominio→IPs para el status file
            domain_ips_map = {}

            for domain in active_domains:
                try:
                    logger.debug(f"[DNS] Resolviendo dominio: {domain}")
                    ips = self.manager.get_domain_ips(domain)
                    domain_ips_map[domain] = ips  # Guardar IPs resueltas para este dominio
                    logger.debug(f"[DNS] Dominio {domain} resuelto a IPs: {ips}")

                    for ip in ips:
                        logger.debug(f"[ROUTES] Intentando aplicar ruta: {ip} via {gateway} dev {local_iface}")
                        if self.manager.apply_route(ip, gateway, local_iface):
                            routes_added += 1
                            applied_routes_set.add(ip)  # Acumular IP aplicada
                            logger.info(f"[ROUTES] Ruta AÑADIDA: {ip} via {gateway} dev {local_iface} (dominio: {domain})")
                        else:
                            logger.debug(f"[ROUTES] Ruta ya existente o no aplicada: {ip}")
                except Exception as e:
                    logger.error(f"[ROUTES] Error procesando dominio activo {domain}: {e}")

            # Guardar rutas acumuladas en archivo (para poder limpiar después)
            routes_list = list(applied_routes_set)
            self._save_applied_routes(routes_list)

            logger.info(f"[ROUTES] Bypass aplicado: {routes_added} rutas añadidas")
            logger.debug(f"[ROUTES] Mapa dominio→IPs: {json.dumps(domain_ips_map, indent=2)}")
            logger.debug(f"[ROUTES] Total rutas acumuladas: {len(routes_list)} → {routes_list}")
            return routes_added, domain_ips_map

        except Exception as e:
            logger.error(f"Error aplicando rutas de bypass: {e}")
            return 0, {}

    def handle_vpn_up(self, interface):
        """Maneja el evento de VPN activada (desde dispatcher)"""
        try:
            logger.info(f"VPN {interface} activada, aplicando bypass...")

            # Aplicar rutas
            routes_added, domain_ips_map = self._apply_bypass_routes(interface)

            # Escribir estado final con VPN activa e IPs aplicadas
            self.write_status_file(vpn_active=True, domain_ips_map=domain_ips_map)

            logger.info(f"VPN up procesado: {routes_added} rutas, {len(domain_ips_map)} dominios con IPs")

        except Exception as e:
            logger.error(f"Error manejando VPN up: {e}")
    
    def handle_vpn_down(self, interface):
        """Maneja el evento de VPN desactivada"""
        try:
            logger.info(f"VPN {interface} desactivada, limpiando rutas...")

            # Limpiar rutas de bypass
            self.clear_bypass_routes()

            # VPN inactiva, limpiar IPs
            self.write_status_file(vpn_active=False, domain_ips_map={})

        except Exception as e:
            logger.error(f"Error manejando VPN down: {e}")

    def _save_applied_routes(self, routes):
        """Guarda las rutas aplicadas en archivo para limpieza posterior"""
        try:
            routes_data = {'routes': routes, 'timestamp': time.time()}
            with open(ROUTES_FILE, 'w') as f:
                json.dump(routes_data, f, indent=2)
            logger.info(f"[JSON_ROUTES] Rutas aplicadas guardadas: {len(routes)}")
            logger.debug(f"[JSON_ROUTES] Contenido guardado en {ROUTES_FILE}:\n{json.dumps(routes_data, indent=2)}")
        except Exception as e:
            logger.error(f"[JSON_ROUTES] Error guardando rutas aplicadas: {e}")

    def _load_applied_routes(self):
        """Carga las rutas que fueron aplicadas por el daemon"""
        try:
            if os.path.exists(ROUTES_FILE):
                with open(ROUTES_FILE, 'r') as f:
                    data = json.load(f)
                    routes = data.get('routes', [])
                    logger.debug(f"[JSON_ROUTES] Rutas cargadas desde {ROUTES_FILE}: {routes}")
                    logger.debug(f"[JSON_ROUTES] Contenido completo: {json.dumps(data, indent=2)}")
                    return routes
            else:
                logger.debug(f"[JSON_ROUTES] Archivo {ROUTES_FILE} no existe, retornando lista vacía")
        except Exception as e:
            logger.error(f"[JSON_ROUTES] Error cargando rutas aplicadas: {e}")
        return []

    def clear_bypass_routes(self):
        """Limpia todas las rutas de bypass aplicadas por el daemon"""
        try:
            logger.info("[CLEANUP] Limpiando rutas de bypass del daemon...")

            # Cargar rutas que aplicamos nosotros (desde archivo, no de memoria)
            applied_routes = self._load_applied_routes()
            logger.debug(f"[CLEANUP] Rutas a limpiar: {applied_routes}")

            routes_cleared = 0
            for dest in applied_routes:
                logger.debug(f"[CLEANUP] Intentando eliminar ruta: {dest}")
                if self.manager.remove_route(dest):
                    routes_cleared += 1
                    logger.info(f"[CLEANUP] Ruta ELIMINADA: {dest}")
                else:
                    logger.debug(f"[CLEANUP] Ruta no pudo ser eliminada: {dest}")

            logger.info(f"[CLEANUP] Total rutas de bypass eliminadas: {routes_cleared}/{len(applied_routes)}")

            # Limpiar el archivo de rutas aplicadas
            self._save_applied_routes([])

            # Rutas limpiadas, IPs vacías, VPN inactiva
            self.write_status_file(vpn_active=False, domain_ips_map={})

        except Exception as e:
            logger.error(f"[CLEANUP] Error limpiando rutas: {e}")
    
    def check_and_apply_routes(self):
        """Verifica estado de VPN y aplica rutas según corresponda"""
        try:
            # Obtener la interfaz VPN configurada
            configured_interface = None
            if self.manager:
                configured_interface = self.manager.get_vpn_interface()

            logger.debug(f"[CHECK] Verificando estado VPN. Interfaz configurada: {configured_interface}")

            if not configured_interface:
                logger.info("[CHECK] No hay interfaz VPN configurada")
                return

            # Verificar si la interfaz está activa usando LOWER_UP
            result = subprocess.run(['ip', 'link', 'show', configured_interface],
                                  capture_output=True, text=True)
            is_active = result.returncode == 0 and 'LOWER_UP' in result.stdout
            logger.debug(f"[CHECK] Estado interfaz {configured_interface}: active={is_active}")
            logger.debug(f"[CHECK] 'ip link show' output: {result.stdout[:200] if result.stdout else 'N/A'}")

            if is_active:
                logger.info(f"[CHECK] VPN {configured_interface} está activa, aplicando rutas de bypass...")
                self.handle_vpn_up(configured_interface)
            else:
                logger.info(f"[CHECK] VPN {configured_interface} no está activa, no se aplican rutas")
                # Notificar VPN inactiva
                self.write_status_file(vpn_active=False)

        except Exception as e:
            logger.error(f"[CHECK] Error verificando estado VPN: {e}")
    
    def reload_domains_and_routes(self):
        """Recarga dominios y reaplica rutas"""
        try:
            logger.info("[RELOAD] Recarga de dominios y rutas solicitada via SIGUSR2")
            # Mostrar configuración actual antes de recargar
            all_domains = self.manager.load_domains()
            active_domains = self.manager.get_active_domains()
            configured_interface = self.manager.get_vpn_interface()
            logger.debug(f"[RELOAD] Configuración actual - Interfaz: {configured_interface}")
            logger.debug(f"[RELOAD] Dominios totales: {all_domains}")
            logger.debug(f"[RELOAD] Dominios activos: {active_domains}")

            # Limpiar rutas antiguas primero (para eliminar rutas de dominios borrados)
            self.clear_bypass_routes()
            # Aplicar nuevas rutas con los dominios actualizados
            self.check_and_apply_routes()
            logger.info("[RELOAD] Recarga completada")
        except Exception as e:
            logger.error(f"[RELOAD] Error recargando dominios y rutas: {e}")
    
    def status(self):
        """Muestra estado actual del daemon y rutas"""
        try:
            print("=== VPN Bypass Daemon Status ===")
            
            # Estado del daemon
            if self.running:
                print("Estado: Activo")
            else:
                print("Estado: Inactivo")
            
            # Dominios configurados
            domains = self.manager.load_domains()
            print(f"Dominios configurados: {len(domains)}")
            for domain in domains:
                ips = self.manager.get_domain_ips(domain)
                print(f"  - {domain}: {len(ips) if ips else 0} IPs")
            
            # Rutas activas
            result = subprocess.run(['ip', 'route', 'show'], 
                                  capture_output=True, text=True, check=True)
            
            routes = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if any(keyword in line.lower() for keyword in ['via', 'dev']) and not 'default' in line:
                    parts = line.split()
                    if parts and not parts[0] == 'default':
                        routes.append(line)
            
            print(f"Rutas activas: {len(routes)}")
            for route in routes[:5]:  # Mostrar primeras 5
                print(f"  - {route}")
            if len(routes) > 5:
                print(f"  ... y {len(routes) - 5} más")
                
        except Exception as e:
            logger.error(f"Error obteniendo estado: {e}")
    
    def run(self):
        """Ejecuta el daemon principal"""
        logger.info("Iniciando VPN Bypass Daemon...")
        self.running = True

        # Enviar estado inicial a la UI
        self.send_initial_vpn_status()

        # Loop principal
        try:
            while self.running:
                time.sleep(5)  # Verificar cada 5 segundos
        except KeyboardInterrupt:
            logger.info("Interrupción recibida, deteniendo daemon...")

        # Limpiar IPs en UI y marcar VPN inactiva
        self.write_status_file(vpn_active=False, domain_ips_map={})
        logger.info("VPN Bypass Daemon detenido")

def kill_existing_daemon():
    """Mata cualquier daemon existente antes de iniciar uno nuevo"""
    try:
        # Buscar procesos del daemon (excluyendo el proceso actual)
        current_pid = os.getpid()
        result = subprocess.run(
            ['pgrep', '-f', DAEMON_SCRIPT_NAME],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            pids = [int(p.strip()) for p in result.stdout.strip().split('\n') if p.strip()]
            # Filtrar el proceso actual y matar los demás
            other_pids = [p for p in pids if p != current_pid]

            if other_pids:
                logger.info(f"Encontrados {len(other_pids)} daemon(s) existente(s), terminando...")
                for pid in other_pids:
                    try:
                        os.kill(pid, signal.SIGTERM)
                        logger.info(f"Enviado SIGTERM a daemon PID {pid}")
                    except ProcessLookupError:
                        pass  # Ya no existe

                # Esperar que terminen (máx 3 segundos)
                import time
                for _ in range(6):
                    time.sleep(0.5)
                    # Verificar si quedan procesos
                    check = subprocess.run(
                        ['pgrep', '-f', DAEMON_SCRIPT_NAME],
                        capture_output=True, text=True
                    )
                    remaining = [int(p.strip()) for p in check.stdout.strip().split('\n')
                                if p.strip() and int(p.strip()) != current_pid]
                    if not remaining:
                        logger.info("Daemon anterior terminado correctamente")
                        return True

                # Si persisten, usar SIGKILL
                logger.warning("Daemon no respondió a SIGTERM, usando SIGKILL...")
                for pid in other_pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                time.sleep(0.5)

    except Exception as e:
        logger.error(f"Error matando daemon existente: {e}")
    return True

def main():
    """Función principal del daemon"""
    global logger

    # Verificar argumento --debug antes de configurar logging
    debug_mode = '--debug' in sys.argv or '-d' in sys.argv
    if debug_mode:
        # Remover --debug/-d de sys.argv para no interferir con otros args
        sys.argv = [arg for arg in sys.argv if arg not in ('--debug', '-d')]

    # Configurar logging (DEBUG si hay flag, INFO por defecto)
    # En modo debug se borra el archivo anterior para tener log limpio
    logger = setup_logging(debug=debug_mode)

    if debug_mode:
        logger.info("[INIT] Modo DEBUG activado - log en /root/vpn_bypass_daemon.log")

    # Verificar dependencias
    deps = check_dependencies()
    missing_deps = [k for k, v in deps.items() if not v]

    if missing_deps:
        logger.error(f"Faltan dependencias: {', '.join(missing_deps)}")
        sys.exit(1)

    # Obtener ruta del directorio actual
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Procesar argumentos especiales primero (no necesitan exclusividad)
    if len(sys.argv) > 1:
        daemon = VPNDaemon(script_dir)
        if sys.argv[1] == "status":
            daemon.status()
            return
        elif sys.argv[1] == "once":
            daemon.check_and_apply_routes()
            return

    # Modo daemon: asegurar exclusividad
    kill_existing_daemon()

    # Crear y ejecutar daemon
    daemon = VPNDaemon(script_dir)
    daemon.run()

if __name__ == "__main__":
    main()
