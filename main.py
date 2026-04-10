#!/usr/bin/env python3
"""
VPN Bypass - Script de instalación
Instala: dependencias, dispatcher, servicio systemd
"""
import sys
import subprocess
import logging


def setup_logging(debug=False):
    """Configura logging básico"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def main():
    """Script de instalación principal"""
    debug = '--debug' in sys.argv or '-d' in sys.argv
    logger = setup_logging(debug)

    if debug:
        sys.argv = [arg for arg in sys.argv if arg not in ('--debug', '-d')]
        logger.info("[INSTALL] Modo DEBUG activado")

    print("=" * 60)
    print("VPN Bypass - Instalación")
    print("=" * 60)
    print()

    # Paso 1: Verificar/instalar tkinter primero (necesario para la UI)
    print("[1/2] Verificando dependencias del sistema...")

    try:
        import tkinter
        print("  ✅ tkinter disponible")
    except ImportError:
        print("  ⚠️  python3-tk no instalado. Instalando...")
        print()
        # Ejecutar de forma interactiva para que el usuario pueda ingresar sudo
        # Ignorar errores de apt update (pueden ser repositorios de terceros)
        print("  Actualizando repositorios (ignorando errores de terceros)...")
        subprocess.run(['sudo', 'apt', 'update'], capture_output=True)

        print("  Instalando python3-tk...")
        result = subprocess.run(['sudo', 'apt', 'install', '-y', 'python3-tk'])
        if result.returncode != 0:
            print("ERROR: No se pudo instalar python3-tk")
            sys.exit(1)
        print("  ✅ python3-tk instalado")
        # Reintentar importar
        try:
            import tkinter
            print("  ✅ tkinter cargado correctamente")
        except ImportError:
            print("ERROR: No se pudo cargar tkinter después de instalar")
            sys.exit(1)

    # Ahora que tkinter está disponible, importar el diálogo de setup
    from setup_dialog import SetupDialog

    dialog = SetupDialog(auto_mode=True)
    deps_ok = dialog.show()

    if not deps_ok:
        print()
        print("=" * 60)
        print("ERROR: No se pudieron instalar las dependencias necesarias")
        print("=" * 60)
        print()
        print("La ventana de instalación se ha quedado abierta mostrando los errores.")
        print("Corrija los problemas e intente nuevamente.")
        sys.exit(1)

    print("✅ Dependencias verificadas")
    print()

    # Paso 2: Instalar configuración del sistema (dispatcher, systemd, etc.)
    print("[2/2] Configurando sistema...")
    from setup_manager import SetupManager

    setup = SetupManager()
    success = setup.run_all_checks()

    if not success:
        print()
        print("=" * 60)
        print("ERROR: La instalación del sistema falló")
        print("=" * 60)
        sys.exit(1)

    print()
    print("=" * 60)
    print("Instalación completada exitosamente!")
    print("=" * 60)
    print()
    print("Archivos instalados:")
    print("  - Dispatcher: /etc/NetworkManager/dispatcher.d/99-vpn-bypass")
    print("  - Servicio: /etc/systemd/system/vpn-bypass.service")
    print("  - Config: domains.yml (en este directorio)")
    print()
    print()
    print("Pasos siguientes:")
    print("  1. Iniciar el daemon: sudo systemctl start vpn-bypass.service")
    print("  2. O iniciar la GUI: python3 gui.py")
    print("  3. El daemon se iniciará automáticamente en el próximo arranque")

if __name__ == "__main__":
    main()
