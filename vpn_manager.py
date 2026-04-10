#!/usr/bin/env python3
"""
Módulo de lógica de negocio para VPN Bypass Manager
Separación completa entre lógica y presentación
"""
import subprocess
import re
import os
import yaml
import threading
import logging
from typing import List, Tuple, Optional, Dict, Any
from config import DOMAINS_FILE

logger = logging.getLogger(__name__)

class VPNManager:
    """Clase principal de gestión de VPN Bypass - Lógica de negocio"""
    
    def __init__(self, script_path: str = None):
        """
        Inicializa el gestor VPN
        
        Args:
            script_path: Ruta al directorio del proyecto (obsoleto, ahora usa archivo YAML)
        """
        # Usar archivo YAML en ubicación estándar del sistema
        self.domains_file = DOMAINS_FILE
        self.script_path = script_path  # Mantener por compatibilidad pero no usar

        # Monitoreo de tráfico con tcpdump
        self.tcpdump_monitor = None

        # Crear directorio del proyecto y archivo YAML si no existe
        domains_dir = os.path.dirname(self.domains_file)
        if domains_dir:
            os.makedirs(domains_dir, exist_ok=True)
        if not os.path.exists(self.domains_file):
            # Crear configuración por defecto en YAML
            default_config = {
                'domains': {
                    'soundcloud.com': {'status': 'activo'},
                    'qwen.ai': {'status': 'activo'},
                    'chat.qwen.ai': {'status': 'activo'}
                },
                'config': {
                    'vpn_interface': 'gpd0'
                }
            }
            with open(self.domains_file, 'w') as f:
                yaml.dump(default_config, f, default_flow_style=False)
            # Establecer permisos permisivos para que daemon (root) y UI (usuario) puedan acceder
            os.chmod(self.domains_file, 0o666)
            logger.info(f"[INIT] Creado {self.domains_file} con permisos 666 (usuario + daemon)")
    
        
    # === GESTIÓN DE DOMINIOS ===
    
    def load_domains(self) -> List[str]:
        """
        Carga los dominios desde archivo YAML
        
        Returns:
            Lista de dominios configurados
        """
        try:
            with open(self.domains_file, 'r') as f:
                data = yaml.safe_load(f)
                return list(data.get('domains', {}).keys())
        except Exception as e:
            raise Exception(f"No se pudieron cargar dominios: {e}")
    
    def save_domains(self, domains: List[str]) -> bool:
        """
        Guarda los dominios en archivo YAML
        
        Args:
            domains: Lista de dominios a guardar
            
        Returns:
            True si se guardaron correctamente, False si hubo error
        """
        try:
            # Cargar configuración existente para preservar estados y config
            data = self._load_yaml_data()
            
            # Actualizar solo los dominios, preservando estados existentes
            existing_domains = data.get('domains', {})
            updated_domains = {}
            
            for domain in domains:
                if domain in existing_domains:
                    updated_domains[domain] = existing_domains[domain]
                else:
                    updated_domains[domain] = {'status': 'activo'}
            
            data['domains'] = updated_domains
            self._save_yaml_file(data)
            return True
        except Exception as e:
            raise Exception(f"No se pudieron guardar dominios: {e}")
    
    def add_domain(self, domain: str) -> bool:
        """
        Añade un nuevo dominio
        
        Args:
            domain: Dominio a añadir
            
        Returns:
            True si se añadió, False si ya existía o es inválido
        """
        domain = domain.strip()
        
        if not domain:
            raise ValueError("El dominio no puede estar vacío")
        
        if not re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain):
            raise ValueError("Formato de dominio inválido")
        
        domains = self.load_domains()
        if domain in domains:
            raise ValueError(f"El dominio '{domain}' ya existe")
        
        domains.append(domain)
        
        # Guardar con estado activo por defecto
        try:
            existing_domains = self._load_domains_with_status()
            existing_domains[domain] = 'activo'
            self._save_domains_with_status(existing_domains)
        except:
            self.save_domains(domains)  # Fallback
        return True
    
    def remove_domain(self, domain: str) -> bool:
        """
        Elimina un dominio
        
        Args:
            domain: Dominio a eliminar
            
        Returns:
            True si se eliminó, False si no existía
        """
        domains = self.load_domains()
        
        if domain in domains:
            domains.remove(domain)
            self.save_domains(domains)
            return True
        
        return False
    
    def remove_domain_by_index(self, index: int) -> bool:
        """
        Elimina un dominio por índice
        
        Args:
            index: Índice del dominio a eliminar (0-based)
            
        Returns:
            True si se eliminó, False si índice inválido
        """
        domains = self.load_domains()
        
        if 0 <= index < len(domains):
            domain = domains[index]
            domains.pop(index)
            self.save_domains(domains)
            return True
        
        return False
    
    # === GESTIÓN DE DOMINIOS CON ESTADO ===
    
    def _load_yaml_data(self) -> Dict[str, Any]:
        """
        Carga todos los datos desde archivo YAML
        
        Returns:
            Diccionario con todos los datos YAML
        """
        try:
            with open(self.domains_file, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {'domains': {}, 'config': {}}

    def _save_yaml_file(self, data: dict) -> None:
        """
        Guarda datos YAML manteniendo permisos permisivos (666) para daemon y UI

        Args:
            data: Diccionario a guardar
        """
        with open(self.domains_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
        # Mantener permisos permisivos para acceso de usuario y daemon
        os.chmod(self.domains_file, 0o666)

    def _load_domains_with_status(self) -> dict:
        """
        Carga dominios con su estado desde archivo YAML
        
        Returns:
            Diccionario {dominio: estado}
        """
        try:
            data = self._load_yaml_data()
            domains_data = data.get('domains', {})
            
            domains_status = {}
            for domain, config in domains_data.items():
                status = config.get('status', 'activo') if isinstance(config, dict) else 'activo'
                domains_status[domain] = status
                
            return domains_status
        except Exception:
            return {}
    
    def _save_domains_with_status(self, domains_status: dict) -> bool:
        """
        Guarda dominios con su estado en formato YAML
        
        Args:
            domains_status: Diccionario {dominio: estado}
            
        Returns:
            True si se guardó correctamente
        """
        try:
            # Cargar configuración existente para preservar
            data = self._load_yaml_data()
            
            # Actualizar dominios con nuevos estados
            updated_domains = {}
            for domain, status in domains_status.items():
                updated_domains[domain] = {'status': status}
            
            data['domains'] = updated_domains
            self._save_yaml_file(data)
            return True
        except Exception as e:
            raise Exception(f"No se pudieron guardar dominios con estado: {e}")
    
    def get_domain_status(self, domain: str) -> str:
        """
        Obtiene el estado de un dominio
        
        Args:
            domain: Dominio a consultar
            
        Returns:
            'activo' o 'inactivo'
        """
        domains_status = self._load_domains_with_status()
        return domains_status.get(domain, 'activo')
    
    def set_domain_status(self, domain: str, status: str) -> bool:
        """
        Cambia el estado de un dominio
        
        Args:
            domain: Dominio a modificar
            status: 'activo' o 'inactivo'
            
        Returns:
            True si se cambió correctamente
        """
        if status not in ['activo', 'inactivo']:
            raise ValueError("Estado debe ser 'activo' o 'inactivo'")
        
        domains_status = self._load_domains_with_status()
        if domain not in domains_status:
            raise ValueError(f"El dominio '{domain}' no existe")
        
        domains_status[domain] = status
        return self._save_domains_with_status(domains_status)
    
    def get_all_domains_with_status(self) -> List[Tuple[str, str]]:
        """
        Obtiene todos los dominios con su estado
        
        Returns:
            Lista de tuplas (dominio, estado)
        """
        domains_status = self._load_domains_with_status()
        return [(domain, status) for domain, status in domains_status.items()]
    
    def get_active_domains(self) -> List[str]:
        """
        Obtiene solo los dominios activos
        
        Returns:
            Lista de dominios activos
        """
        domains_status = self._load_domains_with_status()
        return [domain for domain, status in domains_status.items() if status == 'activo']
    
    # === GESTIÓN DE CONFIGURACIONES ===
    
    def _load_config(self) -> dict:
        """
        Carga configuraciones desde archivo YAML
        
        Returns:
            Diccionario {config_key: config_value}
        """
        try:
            data = self._load_yaml_data()
            return data.get('config', {})
        except Exception:
            return {}
    
    def _save_config(self, config: dict) -> bool:
        """
        Guarda configuraciones en formato YAML
        
        Args:
            config: Diccionario {config_key: config_value}
            
        Returns:
            True si se guardó correctamente
        """
        try:
            # Cargar datos existentes para preservar dominios
            data = self._load_yaml_data()
            
            # Actualizar configuraciones
            data['config'] = config
            self._save_yaml_file(data)
            return True
        except Exception as e:
            raise Exception(f"No se pudieron guardar configuraciones: {e}")
    
    def get_config(self, key: str, default=None):
        """
        Obtiene un valor de configuración
        
        Args:
            key: Clave de configuración
            default: Valor por defecto si no existe
            
        Returns:
            Valor de configuración o default
        """
        config = self._load_config()
        return config.get(key, default)
    
    def set_config(self, key: str, value: str) -> bool:
        """
        Establece un valor de configuración
        
        Args:
            key: Clave de configuración
            value: Valor de configuración
            
        Returns:
            True si se guardó correctamente
        """
        config = self._load_config()
        config[key] = value
        return self._save_config(config)
    
    def get_vpn_interface(self) -> str:
        """
        Obtiene la interfaz VPN configurada
        
        Returns:
            Nombre de la interfaz VPN (por defecto 'gpd0')
        """
        return self.get_config('vpn_interface', 'gpd0')
    
    def set_vpn_interface(self, interface: str) -> bool:
        """
        Establece la interfaz VPN

        Args:
            interface: Nombre de la interfaz VPN

        Returns:
            True si se guardó correctamente
        """
        return self.set_config('vpn_interface', interface)

    def is_vpn_active(self) -> bool:
        """
        Verifica si la interfaz VPN configurada está activa

        Returns:
            True si la interfaz tiene flag UP o LOWER_UP
        """
        try:
            interface = self.get_vpn_interface()
            if not interface:
                return False

            result = subprocess.run(['ip', 'link', 'show', interface],
                                  capture_output=True, text=True)
            return result.returncode == 0 and ('LOWER_UP' in result.stdout or 'UP' in result.stdout)
        except Exception as e:
            logger.error(f"[VPN] Error verificando estado de VPN: {e}")
            return False

    def get_vpn_interfaces_list(self) -> List[str]:
        """
        Obtiene la lista de interfaces VPN disponibles

        Returns:
            Lista de nombres de interfaces VPN configuradas
        """
        interfaces = self.get_config('vpn_interfaces', None)
        if interfaces and isinstance(interfaces, list):
            return interfaces
        # Valores por defecto si no está configurado
        return ['gpd0', 'tun0', 'tun1', 'wg0', 'utun0', 'ppp0']

    # === GESTIÓN DE DNS E IPs ===
    
    def get_domain_ips(self, domain: str) -> List[str]:
        """
        Obtiene las IPs de un dominio específico (soporta comodines)
        
        Args:
            domain: Dominio a resolver (puede contener *)
            
        Returns:
            Lista de IPs del dominio
        """
        result = self.get_domain_ips_with_info(domain)
        return result['ips']

    def get_domain_ips_with_info(self, domain: str) -> dict:
        """
        Obtiene las IPs de un dominio con información detallada de resolución
        
        Args:
            domain: Dominio a resolver (puede contener *)
            
        Returns:
            Dict con {'ips': [...], 'error': None/str, 'status': 'ok'/'timeout'/'nxdomain'/'error'}
        """
        try:
            # Si es un comodín, expandirlo primero
            if '*' in domain:
                ips = self._expand_wildcard_domain(domain)
                return {'ips': ips, 'error': None, 'status': 'ok' if ips else 'no_records'}
            
            # Dominio normal (con timeout de 3 segundos para no bloquear UI)
            result = subprocess.run(['dig', '@8.8.8.8', domain, '+short', '+time=2', '+tries=1'],
                                  capture_output=True, text=True, timeout=3)
            ips = []
            # Procesar stdout incluso si dig retorna error (NXDOMAIN)
            for line in result.stdout.splitlines():
                line = line.strip()
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', line):
                    ips.append(line)
            
            if ips:
                return {'ips': ips, 'error': None, 'status': 'ok'}
            
            # No se encontraron IPs - analizar por qué
            stderr = result.stderr.lower() if result.stderr else ''
            if 'nxdomain' in stderr or 'nxdomain' in result.stdout.lower():
                return {'ips': [], 'error': 'Dominio no existe (NXDOMAIN)', 'status': 'nxdomain'}
            elif 'servfail' in stderr:
                return {'ips': [], 'error': 'Error del servidor DNS (SERVFAIL)', 'status': 'error'}
            elif result.returncode != 0:
                return {'ips': [], 'error': f'Error DNS (código {result.returncode})', 'status': 'error'}
            else:
                return {'ips': [], 'error': 'Dominio sin registros A', 'status': 'no_records'}
                
        except subprocess.TimeoutExpired:
            return {'ips': [], 'error': 'Timeout: sin conexión a DNS (8.8.8.8)', 'status': 'timeout'}
        except FileNotFoundError:
            return {'ips': [], 'error': 'Comando dig no encontrado', 'status': 'error'}
        except Exception as e:
            return {'ips': [], 'error': f'Error: {str(e)}', 'status': 'error'}
    
    def _expand_wildcard_domain(self, wildcard_domain: str) -> List[str]:
        """
        Expande un dominio con comodín para obtener todos los subdominios
        
        Args:
            wildcard_domain: Dominio con comodín (ej: *.qwen.ai)
            
        Returns:
            Lista de IPs de todos los subdominios encontrados
        """
        try:
            # Extraer el dominio base (quitar *.)
            if wildcard_domain.startswith('*.'):
                base_domain = wildcard_domain[2:]
            else:
                # Si no empieza con *, devolver lista vacía
                return []
            
            # Usar transfer de zona para obtener todos los registros
            result = subprocess.run(['dig', '@8.8.8.8', base_domain, 'AXFR'], 
                                  capture_output=True, text=True)
            
            # Si AXFR falla (común en dominios públicos), usar enumeración común
            if result.returncode != 0 or 'Transfer failed' in result.stdout:
                return self._enumerate_common_subdomains(base_domain)
            
            # Parsear resultados de AXFR
            ips = []
            for line in result.stdout.splitlines():
                line = line.strip()
                # Buscar líneas con registros A
                if re.match(r'^[a-zA-Z0-9.-]+\.' + re.escape(base_domain) + r'.*\s+IN\s+A\s+\d+\.\d+\.\d+\.\d+', line):
                    # Extraer IP
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)$', line)
                    if ip_match:
                        ip = ip_match.group(1)
                        if ip not in ips:
                            ips.append(ip)
            
            return ips
            
        except Exception:
            # Fallback a enumeración común
            base_domain = wildcard_domain[2:] if wildcard_domain.startswith('*.') else wildcard_domain
            return self._enumerate_common_subdomains(base_domain)
    
    def _enumerate_common_subdomains(self, base_domain: str) -> List[str]:
        """
        Enumera subdominios comunes para un dominio base
        
        Args:
            base_domain: Dominio base (ej: qwen.ai)
            
        Returns:
            Lista de IPs encontradas
        """
        common_subdomains = [
            'www', 'api', 'app', 'chat', 'cdn', 'img', 'static',
            'admin', 'mail', 'ftp', 'blog', 'shop', 'dev', 'test',
            'staging', 'prod', 'v1', 'v2', 'v3', 'api-v1', 'api-v2'
        ]
        
        all_ips = []
        
        # Probar cada subdominio
        for subdomain in common_subdomains:
            full_domain = f"{subdomain}.{base_domain}"
            try:
                result = subprocess.run(['dig', '@8.8.8.8', full_domain, '+short'], 
                                      capture_output=True, text=True, timeout=3)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        line = line.strip()
                        if re.match(r'^\d+\.\d+\.\d+\.\d+$', line):
                            if line not in all_ips:
                                all_ips.append(line)
            except:
                continue
        
        # También probar el dominio base
        try:
            result = subprocess.run(['dig', '@8.8.8.8', base_domain, '+short'], 
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if re.match(r'^\d+\.\d+\.\d+\.\d+$', line):
                        if line not in all_ips:
                            all_ips.append(line)
        except:
            pass
        
        return all_ips
    
    def get_all_domains_with_ips(self) -> List[Tuple[str, List[str]]]:
        """
        Obtiene todos los dominios con sus IPs
        
        Returns:
            Lista de tuplas (dominio, [ips])
        """
        domains = self.load_domains()
        result = []
        
        for domain in domains:
            ips = self.get_domain_ips(domain)
            result.append((domain, ips))
        
        return result
    
    # === GESTIÓN DE RUTAS IP ===
    
    def get_ip_routes(self) -> List[str]:
        """
        Obtiene todas las rutas IP del sistema
        
        Returns:
            Lista de rutas del sistema
        """
        try:
            result = subprocess.run(['ip', 'route', 'show'], 
                                  capture_output=True, text=True, check=True)
            routes = []
            for line in result.stdout.splitlines():
                if line.strip():
                    routes.append(line.strip())
            return routes
        except subprocess.CalledProcessError:
            return []
        except Exception:
            return []

    def get_traffic_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Obtiene estadísticas de tráfico (bytes y paquetes) por IP destino.
        Requiere el paquete 'iproute2' (comando ss -ti).

        Returns:
            Diccionario {ip: {'bytes_in': int, 'bytes_out': int, 'pkts_in': int, 'pkts_out': int}}
        """
        stats = {}
        try:
            # ss -ti muestra información detallada incluyendo bytes
            result = subprocess.run(['ss', '-ti', 'state', 'established'],
                                  capture_output=True, text=True, check=False, timeout=5)

            import re
            current_ip = None

            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Línea de conexión TCP - peer=IP:port al final
                # Formato: tcp   ESTAB  0  0  local:port  peer=IP:port
                if 'ESTAB' in line or 'ESTABLISHED' in line:
                    # Buscar peer=IP:port
                    peer_match = re.search(r'peer=(\d+\.\d+\.\d+\.\d+):(\d+)', line)
                    if peer_match:
                        current_ip = peer_match.group(1)
                        if current_ip not in stats:
                            stats[current_ip] = {'bytes_in': 0, 'bytes_out': 0, 'pkts_in': 0, 'pkts_out': 0}
                    else:
                        current_ip = None

                # Línea de estadísticas (generalmente indentada)
                elif current_ip and ('bytes_sent' in line or 'bytes_received' in line):
                    # Buscar bytes enviados
                    sent_match = re.search(r'bytes_sent:(\d+)', line)
                    if sent_match:
                        stats[current_ip]['bytes_out'] += int(sent_match.group(1))

                    # Buscar bytes recibidos
                    recv_match = re.search(r'bytes_received:(\d+)', line)
                    if recv_match:
                        stats[current_ip]['bytes_in'] += int(recv_match.group(1))

                    # Estimar paquetes (MTU típico ~1460 bytes payload)
                    if sent_match:
                        sent_bytes = int(sent_match.group(1))
                        pkts_out = max(1, sent_bytes // 1460) if sent_bytes > 0 else 0
                        stats[current_ip]['pkts_out'] += pkts_out
                    if recv_match:
                        recv_bytes = int(recv_match.group(1))
                        pkts_in = max(1, recv_bytes // 1460) if recv_bytes > 0 else 0
                        stats[current_ip]['pkts_in'] += pkts_in

                # Si la línea no está indentada y no es ESTAB, resetear
                elif line and not line.startswith(' ') and not line.startswith('\t'):
                    if 'ESTAB' not in line and 'tcp' not in line.lower():
                        current_ip = None

        except Exception as e:
            print(f"Error en get_traffic_stats: {e}")
            import traceback
            traceback.print_exc()

        return stats

    def start_tcpdump_monitor(self, interface: str, target_ips: List[str]):
        """
        Inicia el monitoreo de tráfico con tcpdump.

        Args:
            interface: Interfaz de red a monitorear
            target_ips: Lista de IPs a monitorear
        """
        if self.tcpdump_monitor is None:
            self.tcpdump_monitor = TCPDumpMonitor()
        self.tcpdump_monitor.start(interface, target_ips)

    def stop_tcpdump_monitor(self):
        """Detiene el monitoreo de tráfico"""
        if self.tcpdump_monitor:
            self.tcpdump_monitor.stop()
            self.tcpdump_monitor = None

    def get_tcpdump_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Obtiene estadísticas del monitoreo tcpdump activo con separación inbound/outbound.
        Retorna {ip: {'pkts_in': int, 'pkts_out': int, 'bytes_in': int, 'bytes_out': int}}
        """
        if self.tcpdump_monitor and self.tcpdump_monitor.is_running():
            return self.tcpdump_monitor.get_stats()
        return {}

    def get_bypass_routes(self) -> List[str]:
        """
        Obtiene solo las rutas de bypass VPN
        
        Returns:
            Lista de rutas que parecen ser de bypass
        """
        try:
            result = subprocess.run(['ip', 'route', 'show'], 
                                  capture_output=True, text=True, check=True)
            bypass_routes = []
            for line in result.stdout.splitlines():
                # Buscar rutas específicas que parezcan de bypass
                if any(keyword in line.lower() for keyword in ['via', 'dev']) and not 'default' in line:
                    bypass_routes.append(line.strip())
            return bypass_routes
        except subprocess.CalledProcessError:
            return []
        except Exception:
            return []
    
    def clear_bypass_routes(self) -> int:
        """
        Limpia las rutas de bypass (requiere sudo)
        
        Returns:
            Número de rutas eliminadas
        """
        try:
            routes = self.get_bypass_routes()
            cleared = 0
            
            for route in routes:
                parts = route.split()
                if parts and not parts[0] == 'default':
                    dest = parts[0]
                    try:
                        subprocess.run(['sudo', 'ip', 'route', 'del', dest], 
                                     capture_output=True, text=True, check=True)
                        cleared += 1
                    except subprocess.CalledProcessError:
                        continue
            
            return cleared
        except Exception:
            return 0
    
    def remove_specific_route(self, destination: str) -> bool:
        """
        Elimina una ruta específica
        
        Args:
            destination: Destino de la ruta a eliminar
            
        Returns:
            True si se eliminó correctamente
        """
        try:
            subprocess.run(['sudo', 'ip', 'route', 'del', destination], 
                         capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False
        except Exception:
            return False
    
    # === UTILIDADES ===
    
    def validate_domain(self, domain: str) -> bool:
        """
        Valida formato de dominio (soporta comodines)
        
        Args:
            domain: Dominio a validar
            
        Returns:
            True si es válido
        """
        domain = domain.strip()
        
        # Permitir comodines *.dominio.com
        if domain.startswith('*.'):
            base_domain = domain[2:]
            return bool(re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', base_domain))
        
        # Dominio normal
        return bool(re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain))
    
    def get_script_info(self) -> dict:
        """
        Obtiene información del script
        
        Returns:
            Diccionario con información del script
        """
        return {
            'script_path': self.script_path,
            'script_exists': os.path.exists(self.script_path),
            'domains_count': len(self.load_domains()),
            'bypass_routes_count': len(self.get_bypass_routes())
        }
    # === MÉTODOS DE GESTIÓN DE RUTAS (RED) ===

    def get_local_gateway_and_iface(self, exclude_interface: str = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Obtiene el gateway e interfaz local para conexión a internet.
        Excluye la interfaz VPN para evitar rutas circulares.

        Args:
            exclude_interface: Interfaz a excluir (normalmente la VPN)

        Returns:
            Tuple (gateway, local_iface) o (None, None) si no se encuentra
        """
        try:
            result = subprocess.run(['ip', 'route', 'show', 'default'],
                                  capture_output=True, text=True, check=True)

            gateway = None
            local_iface = None

            for line in result.stdout.splitlines():
                if 'default' in line:
                    # Si se especifica interfaz a excluir, saltar esa línea
                    if exclude_interface and exclude_interface in line:
                        continue

                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == 'via' and i + 1 < len(parts):
                            gateway = parts[i + 1]
                        elif part == 'dev' and i + 1 < len(parts):
                            local_iface = parts[i + 1]
                    break

            return gateway, local_iface
        except Exception as e:
            print(f"Error obteniendo gateway local: {e}")
            return None, None

    def apply_route(self, dest_ip: str, gateway: str, local_iface: str) -> bool:
        """
        Aplica una ruta de bypass via gateway local.

        Args:
            dest_ip: IP destino (ej: '142.251.110.93' o '142.251.110.93/32')
            gateway: Gateway local
            local_iface: Interfaz local

        Returns:
            True si se aplicó correctamente
        """
        try:
            subprocess.run(
                ['sudo', 'ip', 'route', 'add', dest_ip, 'via', gateway, 'dev', local_iface],
                capture_output=True, text=True, check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error aplicando ruta {dest_ip}: {e}")
            return False

    def remove_route(self, dest_ip: str) -> bool:
        """
        Elimina una ruta de bypass.

        Args:
            dest_ip: IP destino de la ruta a eliminar

        Returns:
            True si se eliminó correctamente (o ya no existía)
        """
        try:
            subprocess.run(
                ['sudo', 'ip', 'route', 'del', dest_ip],
                capture_output=True, text=True, check=True
            )
            return True
        except subprocess.CalledProcessError:
            # La ruta ya no existe, considerar éxito
            return True

    def get_system_routes(self) -> List[str]:
        """
        Obtiene todas las rutas del sistema (excepto default y link-local).

        Returns:
            Lista de destinos (ej: ['192.168.1.0/24', '10.0.0.0/8'])
        """
        try:
            result = subprocess.run(['ip', 'route', 'show'],
                                  capture_output=True, text=True, check=True)

            routes = []
            for line in result.stdout.splitlines():
                line = line.strip()
                # Rutas específicas (no default, no link-local)
                if any(keyword in line.lower() for keyword in ['via', 'dev']) and 'default' not in line:
                    parts = line.split()
                    if parts and parts[0] != 'default' and not parts[0].startswith('fe80'):
                        routes.append(parts[0])
            return routes
        except Exception as e:
            print(f"Error obteniendo rutas del sistema: {e}")
            return []

    def reset_tcpdump_stats(self):
        """Resetea los contadores del monitoreo tcpdump"""
        if self.tcpdump_monitor:
            self.tcpdump_monitor.reset()


class TCPDumpMonitor:
    """
    Monitorea tráfico de red usando tcpdump para IPs específicas.
    Corre en un hilo separado y acumula contadores de paquetes.
    """

    def __init__(self):
        # Contadores separados: inbound (hacia IP) y outbound (desde IP)
        self.pkts_in = {}   # {ip: count} - paquetes entrantes
        self.pkts_out = {}  # {ip: count} - paquetes salientes
        self.bytes_in = {}  # {ip: bytes} - bytes entrantes
        self.bytes_out = {} # {ip: bytes} - bytes salientes
        self._process = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._interface = None
        self._target_ips = set()

    def start(self, interface: str, target_ips: List[str]):
        """
        Inicia el monitoreo en la interfaz especificada para las IPs dadas.

        Args:
            interface: Nombre de la interfaz (ej: 'wlp0s20f3', 'eth0')
            target_ips: Lista de IPs a monitorear (solo parte entera, sin /32)
        """
        if self._running:
            self.stop()

        self._interface = interface
        self._target_ips = set(ip.split('/')[0] if '/' in ip else ip for ip in target_ips)

        if not self._target_ips:
            print("[TCPDumpMonitor] No hay IPs para monitorear")
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"[TCPDumpMonitor] Iniciado en {interface} para {len(self._target_ips)} IPs")

    def _monitor_loop(self):
        """Loop principal que ejecuta tcpdump y parsea la salida"""
        import subprocess
        import re

        # Construir filtro de BPF para las IPs
        # Ejemplo: "dst 52.84.150.52 or dst 52.84.150.45"
        ip_filter = " or ".join([f"host {ip}" for ip in self._target_ips])

        # tcpdump: -i interfaz, -n no resolver DNS, -l buffer de línea, -q quiet
        cmd = ['sudo', 'tcpdump', '-i', self._interface, '-n', '-l', '-q', ip_filter]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Buffer de línea
            )

            # tcpdump -q produce líneas como:
            # 20:31:45.123456 IP 192.168.1.100.54321 > 52.84.150.52.443: tcp 1428
            pattern = re.compile(
                r'IP\s+(\d+\.\d+\.\d+\.\d+)\.\d+\s+>\s+(\d+\.\d+\.\d+\.\d+)\.\d+:.*?(\d+)$'
            )

            while self._running and self._process.poll() is None:
                line = self._process.stdout.readline()
                if not line:
                    continue

                # Parsear la línea
                match = pattern.search(line)
                if match:
                    src_ip = match.group(1)
                    dst_ip = match.group(2)
                    length = int(match.group(3)) if match.group(3) else 0

                    with self._lock:
                        # INBOUND: tráfico dirigido a la IP monitoreada (la recibe)
                        if dst_ip in self._target_ips:
                            self.pkts_in[dst_ip] = self.pkts_in.get(dst_ip, 0) + 1
                            self.bytes_in[dst_ip] = self.bytes_in.get(dst_ip, 0) + length
                        # OUTBOUND: tráfico originado en la IP monitoreada (la envía)
                        if src_ip in self._target_ips:
                            self.pkts_out[src_ip] = self.pkts_out.get(src_ip, 0) + 1
                            self.bytes_out[src_ip] = self.bytes_out.get(src_ip, 0) + length

        except Exception as e:
            print(f"[TCPDumpMonitor] Error: {e}")
        finally:
            self._running = False
            if self._process:
                self._process.terminate()
                try:
                    self._process.wait(timeout=2)
                except:
                    self._process.kill()

    def stop(self):
        """Detiene el monitoreo"""
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except:
                try:
                    self._process.kill()
                except:
                    pass
            self._process = None
        print("[TCPDumpMonitor] Detenido")

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Retorna estadísticas acumuladas separadas inbound/outbound.
        {ip: {'pkts_in': int, 'pkts_out': int, 'bytes_in': int, 'bytes_out': int}}
        """
        with self._lock:
            return {ip: {
                'pkts_in': self.pkts_in.get(ip, 0),
                'pkts_out': self.pkts_out.get(ip, 0),
                'bytes_in': self.bytes_in.get(ip, 0),
                'bytes_out': self.bytes_out.get(ip, 0)
            } for ip in self._target_ips}

    def reset(self):
        """Resetea los contadores"""
        with self._lock:
            self.pkts_in.clear()
            self.pkts_out.clear()
            self.bytes_in.clear()
            self.bytes_out.clear()

    def is_running(self) -> bool:
        """Verifica si el monitoreo está activo"""
        return self._running and self._process is not None and self._process.poll() is None


# === FUNCIONES DE CONVENIENCIA ===

def create_manager(script_dir: str = None) -> VPNManager:
    """
    Crea una instancia de VPNManager
    
    Args:
        script_dir: Ruta al directorio del proyecto (opcional)
        
    Returns:
        Instancia de VPNManager
    """
    return VPNManager(script_dir)

def check_dependencies() -> dict:
    """
    Verifica dependencias del sistema

    Returns:
        Diccionario con estado de dependencias
    """
    deps = {
        'dig': False,
        'ip': False,
        'sudo': False,
        'python3-yaml': False
    }

    try:
        subprocess.run(['dig', '-v'], capture_output=True, check=True)
        deps['dig'] = True
    except:
        pass

    try:
        subprocess.run(['ip', 'route'], capture_output=True, check=True)
        deps['ip'] = True
    except:
        pass

    try:
        subprocess.run(['sudo', '--version'], capture_output=True, check=True)
        deps['sudo'] = True
    except:
        pass

    try:
        import yaml
        deps['python3-yaml'] = True
    except ImportError:
        pass

    return deps


