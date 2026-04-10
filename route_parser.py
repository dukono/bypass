#!/usr/bin/env python3
"""
RouteParser - Parsing de información técnica de rutas de red
"""
from typing import Dict, Any


class RouteParser:
    """Parsea strings de rutas de red a estructuras de datos"""

    @staticmethod
    def parse(route_string: str) -> Dict[str, Any]:
        """
        Parsea una ruta para extraer información técnica detallada

        Args:
            route_string: String de ruta (ej: "default via 192.168.1.1 dev eth0 proto dhcp metric 100")

        Returns:
            Diccionario con campos: destination, gateway, interface, protocol, metric, scope, src, type
        """
        route_info = {
            'destination': 'unknown',
            'gateway': 'N/A',
            'interface': 'N/A',
            'protocol': 'N/A',
            'metric': 'N/A',
            'scope': 'N/A',
            'src': 'N/A',
            'type': 'unknown'
        }

        if not route_string:
            return route_info

        parts = route_string.split()
        i = 0

        while i < len(parts):
            part = parts[i]

            if part == 'default':
                route_info['destination'] = '0.0.0.0/0'
                route_info['type'] = 'default'
            elif part == 'via' and i + 1 < len(parts):
                route_info['gateway'] = parts[i + 1]
                route_info['type'] = 'bypass'
                i += 1
            elif part == 'dev' and i + 1 < len(parts):
                route_info['interface'] = parts[i + 1]
                i += 1
            elif part == 'proto' and i + 1 < len(parts):
                route_info['protocol'] = parts[i + 1]
                i += 1
            elif part == 'metric' and i + 1 < len(parts):
                route_info['metric'] = parts[i + 1]
                i += 1
            elif part == 'scope' and i + 1 < len(parts):
                route_info['scope'] = parts[i + 1]
                i += 1
            elif part == 'src' and i + 1 < len(parts):
                route_info['src'] = parts[i + 1]
                i += 1
            elif '/' in part and '.' in part:  # Es una red CIDR
                route_info['destination'] = part
                if route_info['type'] == 'unknown':
                    route_info['type'] = 'local'
            elif '.' in part and len(part.split('.')) == 4:  # Es una IP
                if route_info['destination'] == 'unknown':
                    route_info['destination'] = part
                    if route_info['type'] == 'unknown':
                        route_info['type'] = 'host'
            i += 1

        return route_info

    @staticmethod
    def is_bypass_route(route_info: Dict[str, Any]) -> bool:
        """Verifica si una ruta es de tipo bypass (tiene gateway)"""
        return route_info.get('type') == 'bypass' or route_info.get('gateway') != 'N/A'

    @staticmethod
    def is_default_route(route_info: Dict[str, Any]) -> bool:
        """Verifica si es ruta por defecto"""
        return route_info.get('type') == 'default'

    @staticmethod
    def format_destination(route_info: Dict[str, Any]) -> str:
        """Formatea el destino para visualización"""
        dest = route_info.get('destination', 'unknown')
        if dest == '0.0.0.0/0':
            return 'default'
        return dest
