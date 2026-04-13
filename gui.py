#!/usr/bin/env python3
"""
Interfaz Gráfica para VPN Bypass Manager - Versión con archivos JSON (sin D-Bus)
Separación completa entre lógica y presentación con System Tray
"""
import sys
import os
import re
import logging
import subprocess
from typing import Optional

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import json
from vpn_manager import VPNManager, create_manager
from config import STATUS_FILE, DOMAINS_FILE
from daemon_controller import DaemonController
from file_watcher import FileWatcher
from traffic_monitor import TrafficMonitor
from route_parser import RouteParser

# Configuración de logging (por defecto INFO, DEBUG con --debug)
def setup_logging(debug=False):
    """Configura el logging con nivel INFO por defecto, DEBUG con flag"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

# Logger inicial (INFO por defecto, se reconfigura si hay --debug)
logger = setup_logging(debug=False)

# Obtener directorio del script para rutas relativas
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class VPNBypassGUI:
    """Interfaz gráfica para VPN Bypass Manager - Capa de presentación"""

    def __init__(self, root):
        self.root = root
        self.root.title("VPN Bypass - Gestor Completo")
        self.root.geometry("850x700")

        # Inicializar componentes de lógica
        self._init_components()

        # Configurar tema oscuro global
        self.setup_dark_theme()

        # Modificar comportamiento de cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_window_close)

        # Crear interfaz
        self.create_widgets()

        # Verificar estado inicial del daemon (solo muestra estado, no inicia)
        self.check_daemon_status()

        # Cargar datos iniciales
        self.refresh_data()

        # Iniciar monitoreo del estado via file watching
        self._start_file_watching()

        # Iniciar monitoreo periódico de tráfico
        self._start_traffic_monitoring()

    def _init_components(self) -> None:
        """Inicializa todos los componentes de lógica"""
        # Gestionar de lógica de dominios y rutas
        try:
            self.manager = create_manager(SCRIPT_DIR)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo inicializar el gestor: {e}")
            sys.exit(1)

        # Almacenar IPs por dominio desde el daemon
        self._domain_ips_from_daemon = {}

        # Controlador de daemon
        self.daemon_controller = DaemonController()
        self.daemon_controller.register_status_callback(self._on_daemon_status_change)

        # Watcher de archivo de estado
        self._status_watcher: Optional[FileWatcher] = None

        # Monitor de tráfico
        self._traffic_monitor: Optional[TrafficMonitor] = None
        self._tcpdump_running = False

    def _on_daemon_status_change(self, is_running: bool) -> None:
        """Callback para cambios de estado del daemon"""
        self._update_daemon_ui(is_running)
        if not is_running and self._domain_ips_from_daemon:
            self._domain_ips_from_daemon = {}
            self.refresh_domains()

    def _update_daemon_ui(self, is_running: bool) -> None:
        """Actualiza la UI del estado del daemon"""
        if is_running:
            pid = self.daemon_controller.get_pid()
            status_text = f"🟢 Daemon Activo (PID: {pid})" if pid else "🟢 Daemon Activo"
            if self.daemon_controller.uses_systemd():
                status_text += " [systemd]"
            self.daemon_status_label.config(text=status_text, foreground='#4CAF50')
        else:
            status_text = "🔴 Daemon Inactivo"
            if self.daemon_controller.uses_systemd():
                status_text += " [systemd]"
            self.daemon_status_label.config(text=status_text, foreground='#F44336')

    def _create_github_style_button(self, parent_frame) -> None:
        """Crea botón estilo GitHub: acción principal + dropdown"""
        # Frame contenedor
        btn_container = tk.Frame(parent_frame, bg='#4a90e2')
        btn_container.grid(row=0, column=4, columnspan=2, sticky=tk.E, padx=(0, 5))

        # Botón principal (Reiniciar)
        self.restart_daemon_btn = tk.Button(
            btn_container, text="🔄 Reiniciar",
            command=self.restart_daemon,
            bg='#4a90e2', fg='white', font=('Segoe UI', 10, 'bold'),
            activebackground='#357abd', activeforeground='white',
            relief='flat', borderwidth=0, cursor='hand2'
        )
        self.restart_daemon_btn.pack(side=tk.LEFT, fill=tk.Y)

        # Separador visual
        separator = tk.Frame(btn_container, bg='#357abd', width=1)
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=1)

        # Botón dropdown
        self.daemon_dropdown_btn = tk.Button(
            btn_container, text="▼",
            command=self._show_daemon_menu,
            bg='#4a90e2', fg='white', font=('Segoe UI', 8),
            activebackground='#357abd', activeforeground='white',
            relief='flat', borderwidth=0, width=2, cursor='hand2'
        )
        self.daemon_dropdown_btn.pack(side=tk.LEFT, fill=tk.Y)

        # Menú popup
        self.daemon_menu = tk.Menu(self.root, tearoff=0, bg='white', fg='black',
                                   font=('Segoe UI', 10), activebackground='#4a90e2',
                                   activeforeground='white')
        self.daemon_menu.add_command(label="▶️  Iniciar", command=self.start_daemon)
        self.daemon_menu.add_command(label="⏹️  Detener", command=self.stop_daemon)
        self.daemon_menu.add_separator()
        self.daemon_menu.add_command(label="🔄 Reiniciar", command=self.restart_daemon)

    def _show_daemon_menu(self) -> None:
        """Muestra el menú dropdown del daemon"""
        try:
            x = self.daemon_dropdown_btn.winfo_rootx()
            y = self.daemon_dropdown_btn.winfo_rooty() + self.daemon_dropdown_btn.winfo_height()
            self.daemon_menu.post(x, y)
        except Exception as e:
            logger.error(f"[UI] Error mostrando menú: {e}")

    def start_daemon(self) -> None:
        """Inicia el daemon"""
        try:
            self.restart_daemon_btn.config(state='disabled', text='Iniciando...')
            self.root.update()

            def _do_start():
                try:
                    result = self.daemon_controller.start()
                    if result:
                        logger.info("[DAEMON] Iniciado correctamente")
                    else:
                        logger.error("[DAEMON] Falló al iniciar")
                except Exception as e:
                    logger.error(f"[DAEMON] Error iniciando: {e}")
                finally:
                    self.restart_daemon_btn.config(state='normal', text='🔄 Reiniciar')
                    self.check_daemon_status()

            self.root.after(100, _do_start)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo iniciar el daemon: {str(e)}")
            self.check_daemon_status()

    def stop_daemon(self) -> None:
        """Detiene el daemon"""
        try:
            self.restart_daemon_btn.config(state='disabled', text='Deteniendo...')
            self.root.update()

            def _do_stop():
                try:
                    result = self.daemon_controller.stop()
                    if result:
                        logger.info("[DAEMON] Detenido correctamente")
                    else:
                        logger.error("[DAEMON] Falló al detener")
                except Exception as e:
                    logger.error(f"[DAEMON] Error deteniendo: {e}")
                finally:
                    self.restart_daemon_btn.config(state='normal', text='🔄 Reiniciar')
                    self.check_daemon_status()

            self.root.after(100, _do_stop)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo detener el daemon: {str(e)}")
            self.check_daemon_status()

    def _start_file_watching(self) -> None:
        """Inicia el file watcher para el archivo de estado"""
        self._status_watcher = FileWatcher(
            file_path=STATUS_FILE,
            callback=self.read_status_file
        )
        self._status_watcher.start()

        # Leer estado inicial inmediatamente (el watcher solo detecta cambios futuros)
        self.read_status_file()

    def _start_traffic_monitoring(self) -> None:
        """Inicia el monitoreo periódico de tráfico"""
        self._traffic_monitor = TrafficMonitor(
            callback=self._update_traffic,
            interval_ms=5000
        )
        self._traffic_monitor.start(tk_root=self.root)

    def _update_traffic(self) -> None:
        """Callback para actualizar tráfico (solo si hay rutas visibles)"""
        try:
            if self.routes_tree.get_children():
                self.refresh_routes()
        except Exception as e:
            logger.error(f"[TRAFFIC] Error actualizando tráfico: {e}")

    def start_file_watcher(self):
        """Inicia file watcher para detectar cambios en archivos de estado via polling"""
        try:
            self._start_polling_watcher()
        except Exception as e:
            logger.error(f"[WATCHER] Error iniciando file watcher: {e}")
    
    def _start_polling_watcher(self):
        """Inicia polling periódico para detectar cambios en archivos"""
        self._last_status_data = {}

        def poll_files():
            while True:
                try:
                    time.sleep(2)  # Verificar cada 2 segundos

                    # Verificar cambios en archivo de estado unificado
                    if os.path.exists(STATUS_FILE):
                        with open(STATUS_FILE, 'r') as f:
                            data = json.load(f)
                            # Comparar con último estado conocido
                            if data != self._last_status_data:
                                self._last_status_data = data.copy()
                                self.root.after(0, self.read_status_file)

                except Exception as e:
                    logger.error(f"[WATCHER] Error en polling: {e}")

        # Iniciar thread de polling
        import threading
        poll_thread = threading.Thread(target=poll_files, daemon=True)
        poll_thread.start()
        logger.info("[WATCHER] Polling de archivos iniciado (2s intervalo)")

    def read_status_file(self):
        """Lee archivo de estado del daemon (solo datos, no estado del proceso)"""
        try:
            vpn_active = None
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, 'r') as f:
                    data = json.load(f)

                    # Solo leer estado VPN - daemon_running se verifica via pgrep
                    vpn_active = data.get('vpn_active')

                    # Leer IPs por dominio desde el daemon
                    domain_ips = data.get('domain_ips', None)
                    if domain_ips is not None:
                        self._domain_ips_from_daemon = domain_ips
                        self.refresh_domains()
            else:
                # Archivo no existe: limpiar IPs
                if self._domain_ips_from_daemon:
                    self._domain_ips_from_daemon = {}
                    self.refresh_domains()

            vpn_interface = self.manager.get_vpn_interface() if self.manager else None
            self.update_vpn_status(vpn_active, vpn_interface)

        except Exception as e:
            logger.error(f"[STATUS] Error leyendo estado: {e}")

    def setup_dark_theme(self):
        """Configura el tema oscuro para toda la aplicación"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configurar colores base del tema
        bg_color = '#2b2b2b'
        fg_color = 'white'
        select_color = '#4a90e2'
        button_color = '#353535'
        frame_color = '#333333'
        
        # Configurar estilos globales
        style.configure('TFrame', background=frame_color)
        style.configure('TLabelframe', background=frame_color, foreground='white')
        style.configure('TLabelframe.Label', background=frame_color, foreground='white', font=('Segoe UI', 10, 'bold'))
        style.configure('TLabel', background=frame_color, foreground='white', font=('Segoe UI', 10))
        style.configure('TButton', background=button_color, foreground='white', font=('Segoe UI', 10, 'bold'))
        style.configure('TButton.Disabled.TButton', background='#1a1a1a', foreground='#666666', font=('Segoe UI', 10, 'bold'))
        style.configure('TEntry', fieldbackground='#1e1e1e', foreground='white', font=('Segoe UI', 10))
        
        # Configurar mapa de colores para botones
        style.map('TButton',
                 background=[('active', '#4a90e2'), ('!active', button_color)],
                 foreground=[('active', 'white'), ('!active', 'white')])
        
        # Aplicar color de fondo a la ventana principal
        self.root.configure(bg=bg_color)
    
    def on_window_close(self):
        """Manejador de evento de cierre de ventana"""
        # Cerrar directamente la aplicación
        self.quit_application()
    
    def quit_application(self) -> None:
        """Cierra la interfaz sin detener el daemon"""
        # Detener tcpdump si está corriendo
        if self._tcpdump_running:
            self.manager.stop_tcpdump_monitor()

        # Detener componentes de monitoreo
        if self._status_watcher:
            self._status_watcher.stop()
        if self._traffic_monitor:
            self._traffic_monitor.stop()

        # Cerrar ventana inmediatamente sin tocar el daemon
        if self.root:
            self.root.quit()
            self.root.destroy()

        sys.exit(0)
    
    def create_widgets(self):
        """Crea los widgets de la interfaz con estilo moderno"""

        # Frame principal con estilo oscuro
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configurar grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=0)  # Estado daemon
        main_frame.rowconfigure(1, weight=1)  # PanedWindow dominios/rutas

        # === SECCIÓN SUPERIOR: ESTADO DEL DAEMON ===
        self.create_daemon_status_frame(main_frame)

        # === PANEDWINDOW: DOMINIOS Y RUTAS CON RESIZER ===
        self.create_paned_sections(main_frame)
        
    
    def create_daemon_status_frame(self, parent):
        """Crea la sección de estado del daemon y configuración de interfaz VPN"""
        status_frame = ttk.Frame(parent, padding="5")
        status_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        status_frame.columnconfigure(2, weight=1)

        # Izquierda: Estado VPN
        self.vpn_status_label = ttk.Label(status_frame, text="VPN:",
                                        font=('Segoe UI', 10), foreground='#aaaaaa')
        self.vpn_status_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 10))

        # Seguido: Configuración de interfaz VPN
        ttk.Label(status_frame, text="Interfaz VPN:", font=('Segoe UI', 10)).grid(row=0, column=1, sticky=tk.W, padx=(0, 5))

        self.vpn_interface_var = tk.StringVar()

        # Obtener lista de interfaces VPN desde configuración
        vpn_interfaces = self.manager.get_vpn_interfaces_list()

        self.vpn_interface_combo = ttk.Combobox(status_frame, textvariable=self.vpn_interface_var,
                                                  values=vpn_interfaces, width=10, font=('Segoe UI', 10),
                                                  state='readonly')
        self.vpn_interface_combo.grid(row=0, column=2, sticky=tk.W, padx=(0, 15))

        # Cargar valor actual de la interfaz VPN
        current_interface = self.manager.get_vpn_interface()
        if current_interface in vpn_interfaces:
            self.vpn_interface_var.set(current_interface)
        else:
            # Si no está en la lista, seleccionar el primero por defecto
            self.vpn_interface_var.set(vpn_interfaces[0])

        # Bind cambio de selección para guardar
        self.vpn_interface_combo.bind('<<ComboboxSelected>>', lambda e: self.save_vpn_interface())

        # Centro: Estado del daemon
        self.daemon_status_label = ttk.Label(status_frame, text="Verificando...",
                                          font=('Segoe UI', 10, 'bold'))
        self.daemon_status_label.grid(row=0, column=3, sticky=tk.W+tk.E, padx=(0, 15))

        # Derecha: Botón estilo GitHub (principal + dropdown)
        self._create_github_style_button(status_frame)
    
    def save_vpn_interface(self):
        """Guarda la configuración de la interfaz VPN"""
        try:
            new_interface = self.vpn_interface_var.get()

            # Obtener interfaz actual configurada
            current_interface = self.manager.get_vpn_interface()

            # Solo guardar si hay un cambio real
            if new_interface == current_interface:
                logger.debug(f"[VPN] Interfaz VPN sin cambios: {new_interface}")
                return

            # Guardar configuración
            if self.manager.set_vpn_interface(new_interface):
                logger.info(f"[VPN] Interfaz VPN cambiada: {current_interface} → {new_interface}")
                # Notificar al daemon del cambio
                self._notify_daemon_domains_changed()
            else:
                logger.error("[VPN] Error al guardar la interfaz VPN")

        except Exception as e:
            logger.error(f"[VPN] Error guardando interfaz VPN: {e}")
    
    def update_vpn_status(self, is_active, interface: str = None):
        """Actualiza el indicador de estado VPN en la UI"""
        try:
            if is_active is None:
                # Estado desconocido: daemon no está monitoreando
                self.vpn_status_label.config(text="VPN: Desconocido", foreground='#FF9800')  # Naranja
            elif is_active:
                self.vpn_status_label.config(text="VPN: Activa", foreground='#4CAF50')  # Verde
            else:
                self.vpn_status_label.config(text="VPN: Inactiva", foreground='#F44336')  # Rojo

            # Refrescar dominios y rutas con delay de 0.5s para dar tiempo al daemon de aplicar/quitar rutas
            self.root.after(100, self._delayed_refresh_data)
        except Exception as e:
            logger.error(f"[VPN] Error actualizando estado VPN: {e}")

    def _delayed_refresh_data(self):
        """Refresca dominios y rutas (llamado con delay después de cambio de VPN)"""
        try:
            self.refresh_domains()
            self.refresh_routes()
        except Exception as e:
            logger.error(f"[REFRESH] Error en refresco delayed: {e}")
    
    def create_paned_sections(self, parent):
        """Crea las secciones de dominios y rutas con Notebook (pestañas)"""
        # Notebook para pestañas: Dominios y Rutas
        style = ttk.Style()
        style.configure('TNotebook', background='#333333', tabmargins=[2, 5, 2, 0])
        style.configure('TNotebook.Tab', background='#3c3c3c', foreground='white',
                       font=('Segoe UI', 10, 'bold'), padding=[10, 5])
        style.map('TNotebook.Tab',
                  background=[('selected', '#4a90e2'), ('!selected', '#3c3c3c')],
                  foreground=[('selected', 'white'), ('!selected', '#aaaaaa')])

        self.notebook = ttk.Notebook(parent, style='TNotebook')
        self.notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))

        # === PESTAÑA 1: DOMINIOS ===
        domains_tab = tk.Frame(self.notebook, bg='#333333')
        self.notebook.add(domains_tab, text='Dominios')
        self._setup_domains_content(domains_tab)

        # === PESTAÑA 2: RUTAS ===
        routes_tab = tk.Frame(self.notebook, bg='#333333')
        self.notebook.add(routes_tab, text='Rutas')
        self._setup_routes_content(routes_tab)


    def _setup_domains_content(self, parent):
        """Configura el contenido de la pestaña de dominios"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # Frame para añadir dominio
        add_frame = ttk.Frame(parent, padding="5")
        add_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        add_frame.columnconfigure(1, weight=1)

        ttk.Label(add_frame, text="Dominio:").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        self.domain_entry = ttk.Entry(add_frame, width=35, font=('Segoe UI', 10))
        self.domain_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 8))
        self.domain_entry.bind('<Return>', lambda e: self.add_domain())

        add_button = ttk.Button(add_frame, text="Añadir", command=self.add_domain, width=12)
        add_button.grid(row=0, column=2)

        # Frame de lista de dominios (sin marco)
        list_frame = ttk.Frame(parent, padding="5")
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        # Treeview jerárquico para dominios con IPs desplegables
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Crear estilo personalizado para el Treeview
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configurar estilo del Treeview principal
        style.configure('Custom.Treeview',
                       background='#2b2b2b',
                       foreground='white',
                       fieldbackground='#2b2b2b',
                       bordercolor='#444444',
                       lightcolor='#444444',
                       darkcolor='#444444',
                       font=('Segoe UI', 10))
        
        # Configurar estilo de las cabeceras
        style.configure('Custom.Treeview.Heading',
                       background='#3c3c3c',
                       foreground='white',
                       font=('Segoe UI', 11, 'bold'),
                       relief='flat')
        
        # Configurar estilo para líneas seleccionadas
        style.configure('Custom.Treeview.Selection',
                       background='#4a90e2',
                       foreground='white')
        
        # Configurar mapa de colores para efectos hover
        style.map('Custom.Treeview',
                 background=[('selected', '#4a90e2'),
                           ('!selected', '#2b2b2b')],
                 foreground=[('selected', 'white'),
                           ('!selected', 'white')])
        
        self.domain_tree = ttk.Treeview(list_frame, yscrollcommand=scrollbar.set, 
                                       height=15, style='Custom.Treeview')
        self.domain_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.config(command=self.domain_tree.yview)
        
        # Configurar columnas del Treeview con columna de acciones (cesta)
        self.domain_tree['columns'] = ('info', 'status', 'actions')
        self.domain_tree.column('#0', width=200, minwidth=150, anchor='w')
        self.domain_tree.column('info', width=220, minwidth=150, anchor='w')
        self.domain_tree.column('status', width=100, minwidth=80, anchor='center')
        self.domain_tree.column('actions', width=40, minwidth=30, anchor='center')
        self.domain_tree.heading('#0', text='Dominio', anchor='w')
        self.domain_tree.heading('info', text='Información', anchor='w')
        self.domain_tree.heading('status', text='Estado', anchor='center')
        self.domain_tree.heading('actions', text='', anchor='center')
        
        # Eventos: clic para eliminar (si es en columna cesta), doble clic para toggle
        self.domain_tree.bind('<Button-1>', self.on_domain_click)
        self.domain_tree.bind('<Double-1>', self.on_domain_double_click)
        
        # Configurar estilos visuales para diferentes tipos de nodos
        self.domain_tree.tag_configure('domain', 
                                     background='#353535',
                                     foreground='#4CAF50',
                                     font=('Segoe UI', 11, 'bold'))
        
        self.domain_tree.tag_configure('ip', 
                                     background='#2b2b2b',
                                     foreground='#81C784',
                                     font=('Consolas', 10))
        
        self.domain_tree.tag_configure('no_ip', 
                                     background='#353535',
                                     foreground='#FF9800',
                                     font=('Segoe UI', 10, 'italic'))
        
        # Configurar colores alternados para mejor legibilidad
        self.domain_tree.tag_configure('alt1', background='#2b2b2b')
        self.domain_tree.tag_configure('alt2', background='#333333')
    
    def _setup_routes_content(self, parent):
        """Configura el contenido de la pestaña de rutas"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        # Frame de lista de rutas (sin marco)
        routes_list_frame = ttk.Frame(parent, padding="5")
        routes_list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        routes_list_frame.columnconfigure(0, weight=1)
        routes_list_frame.rowconfigure(0, weight=1)
        
        # Treeview para mostrar rutas con estilo consistente
        routes_scrollbar = ttk.Scrollbar(routes_list_frame)
        routes_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Configurar estilo para el Treeview de rutas
        style = ttk.Style()
        style.configure('Routes.Treeview',
                       background='#2b2b2b',
                       foreground='white',
                       fieldbackground='#2b2b2b',
                       font=('Consolas', 10))

        # Configurar estilo de las cabeceras (igual que dominios)
        style.configure('Routes.Treeview.Heading',
                       background='#3c3c3c',
                       foreground='white',
                       font=('Segoe UI', 11, 'bold'),
                       relief='flat')
        
        self.routes_tree = ttk.Treeview(routes_list_frame, yscrollcommand=routes_scrollbar.set, 
                                       height=12, style='Routes.Treeview')
        self.routes_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        routes_scrollbar.config(command=self.routes_tree.yview)
        
        # Configurar columnas técnicas para el Treeview de rutas
        self.routes_tree['columns'] = ('gateway', 'interface', 'pkts', 'in', 'out', 'protocol', 'metric')
        self.routes_tree.column('#0', width=140, minwidth=120, anchor='w')
        self.routes_tree.column('gateway', width=100, minwidth=90, anchor='center')
        self.routes_tree.column('interface', width=60, minwidth=50, anchor='center')
        self.routes_tree.column('pkts', width=60, minwidth=50, anchor='center')
        self.routes_tree.column('in', width=70, minwidth=55, anchor='center')
        self.routes_tree.column('out', width=70, minwidth=55, anchor='center')
        self.routes_tree.column('protocol', width=60, minwidth=50, anchor='center')
        self.routes_tree.column('metric', width=50, minwidth=45, anchor='center')

        # Cabeceras técnicas
        self.routes_tree.heading('#0', text='Destino/CIDR', anchor='w')
        self.routes_tree.heading('gateway', text='Gateway', anchor='center')
        self.routes_tree.heading('interface', text='Iface', anchor='center')
        self.routes_tree.heading('pkts', text='Pkts', anchor='center')
        self.routes_tree.heading('in', text='▼ Down', anchor='center')
        self.routes_tree.heading('out', text='▲ Up', anchor='center')
        self.routes_tree.heading('protocol', text='Proto', anchor='center')
        self.routes_tree.heading('metric', text='Met', anchor='center')
        
        # Configurar estilos para diferentes tipos de rutas
        self.routes_tree.tag_configure('bypass', background='#353535', foreground='#4CAF50', font=('Consolas', 10, 'bold'))
        self.routes_tree.tag_configure('default', background='#2b2b2b', foreground='#81C784', font=('Consolas', 10))
        self.routes_tree.tag_configure('system', background='#333333', foreground='#FF9800', font=('Consolas', 10))

        # Variable para controlar estado del monitor tcpdump (automático)
        self._tcpdump_running = False

    # === MÉTODOS DE INTERFAZ (DELEGAN A LA LÓGICA) ===
    
    def refresh_data(self):
        """Refresca todos los datos"""
        self.refresh_domains()
        self.refresh_routes()
    
    def refresh_domains(self):
        """Refresca el árbol de dominios con estado checkbox y IPs desplegables"""
        try:
            # Limpiar árbol existente
            for item in self.domain_tree.get_children():
                self.domain_tree.delete(item)
            
            # Obtener dominios con estado
            domains_with_status = self.manager.get_all_domains_with_status()
            
            # Añadir dominios como nodos padres con IPs como nodos hijos
            for i, (domain, status) in enumerate(domains_with_status):
                # Solo usar IPs del daemon (no resolver por DNS desde la UI)
                if domain in self._domain_ips_from_daemon and self._domain_ips_from_daemon[domain]:
                    ips = self._domain_ips_from_daemon[domain]
                    ip_source = "Aplicada por daemon"
                else:
                    # Daemon no tiene IPs para este dominio (apagado o no aplicado)
                    ips = []
                    ip_source = None

                # Determinar colores alternados para mejor legibilidad
                alt_tag = 'alt1' if i % 2 == 0 else 'alt2'

                # Estado para mostrar (checkbox)
                status_text = "✓ Activo" if status == 'activo' else "✗ Inactivo"
                status_color = '#4CAF50' if status == 'activo' else '#F44336'

                if ips:
                    # Nodo padre: dominio con estado, info y icono cesta
                    domain_node = self.domain_tree.insert('', 'end',
                                                         text=domain,
                                                         values=(f"{len(ips)} IPs", status_text, "🗑️"),
                                                         tags=('domain', alt_tag))

                    # Nodos hijos: cada IP con formato mejorado
                    for j, ip in enumerate(ips):
                        ip_tag = f'ip_{alt_tag}'
                        self.domain_tree.tag_configure(ip_tag,
                                                     background='#2b2b2b' if j % 2 == 0 else '#333333',
                                                     foreground='#81C784',
                                                     font=('Consolas', 10))

                        self.domain_tree.insert(domain_node, 'end',
                                              text=f"  {ip}",
                                              values=(ip_source, "", ""),
                                              tags=(ip_tag,))
                else:
                    # Dominio sin IPs - mostrar solo el dominio sin IPs
                    display_msg = "Sin IPs aplicadas" if not self._domain_ips_from_daemon else "Sin resolución"
                    self.domain_tree.insert('', 'end',
                                          text=domain,
                                          values=(display_msg, status_text, "🗑️"),
                                          tags=('no_ip', alt_tag))
            
            # Expandir todos los nodos para mostrar las IPs
            for domain_node in self.domain_tree.get_children():
                self.domain_tree.item(domain_node, open=True)
                
        except Exception as e:
            logger.error(f"[DOMAINS] Error al cargar dominios: {e}")
    
    def on_domain_double_click(self, event):
        """Maneja el doble clic para cambiar el estado de un dominio"""
        try:
            # Obtener elemento seleccionado
            selection = self.domain_tree.selection()
            if not selection:
                return
            
            item = selection[0]
            item_text = self.domain_tree.item(item)['text']
            
            # Ignorar nodos hijos (IPs) - solo procesar dominios
            if item_text.startswith('  '):  # Es una IP (tiene espacios)
                return
            
            # Extraer el dominio
            domain = item_text.strip()
            if not domain:
                return
            
            # Obtener estado actual
            current_status = self.manager.get_domain_status(domain)
            new_status = 'inactivo' if current_status == 'activo' else 'activo'
            
            # Cambiar estado
            self.manager.set_domain_status(domain, new_status)
            
            # Refrescar la lista
            self.refresh_domains()
            
            # Notificar al daemon
            self._notify_daemon_domains_changed()
            
            logger.info(f"[DOMAINS] Dominio {domain} cambiado a {new_status}")
            
        except Exception as e:
            logger.error(f"[DOMAINS] Error cambiando estado del dominio: {e}")

    def on_domain_click(self, event):
        """Maneja el clic simple para detectar clic en botón eliminar"""
        try:
            # Obtener la región y columna del clic
            region = self.domain_tree.identify_region(event.x, event.y)
            if region != "cell":
                return

            # Obtener la columna clicada
            column = self.domain_tree.identify_column(event.x)
            if column != '#3':  # Columna de acciones (eliminar)
                return

            # Obtener el item
            item = self.domain_tree.identify_row(event.y)
            if not item:
                return

            # Obtener el texto del item (nombre del dominio)
            item_text = self.domain_tree.item(item)['text']
            if item_text.startswith('  '):  # Es una IP, ignorar
                return

            domain = item_text.strip()
            if not domain:
                return

            # Confirmar eliminación
            if messagebox.askyesno("Confirmar", f"¿Eliminar dominio '{domain}'?"):
                self.manager.remove_domain(domain)
                self.refresh_domains()
                self.refresh_routes()
                self._notify_daemon_domains_changed()
                logger.info(f"[DOMAINS] Dominio {domain} eliminado correctamente")

        except Exception as e:
            logger.error(f"[DOMAINS] Error eliminando dominio: {e}")

    def add_domain(self):
        """Añade un nuevo dominio"""
        domain = self.domain_entry.get().strip()
        
        if not domain:
            logger.warning("[DOMAINS] Por favor ingrese un dominio")
            return
        
        try:
            # Verificar si tenemos permisos para escribir en el archivo del sistema
            if not self._check_domains_file_permissions():
                if not self._request_sudo_for_domains():
                    messagebox.showerror("Error", "No se pueden guardar dominios sin permisos de administrador")
                    return
            
            self.manager.add_domain(domain)
            self.domain_entry.delete(0, tk.END)
            self.refresh_domains()
            self.refresh_routes()
            self._notify_daemon_domains_changed()
            logger.info(f"[DOMAINS] Dominio {domain} añadido correctamente")
        except ValueError as e:
            messagebox.showwarning("Dominio duplicado", str(e))
        except PermissionError as e:
            messagebox.showerror("Error de Permisos", f"No se pudo añadir el dominio: {str(e)}")
        except Exception as e:
            logger.error(f"[DOMAINS] No se pudo añadir el dominio: {e}")

    def refresh_routes(self):
        """Actualiza la visualización de rutas configuradas agrupadas por dominio"""
        try:
            # Obtener dominios activos y sus IPs
            domains_with_status = self.manager.get_all_domains_with_status()
            routes = self.manager.get_ip_routes()  # Todas las rutas del kernel

            # Limpiar árbol existente
            for item in self.routes_tree.get_children():
                self.routes_tree.delete(item)

            if not routes:
                # Insertar mensaje informativo
                self.routes_tree.insert('', 'end', text="No hay rutas configuradas",
                                      values=("N/A", "N/A", "N/A", "N/A", "N/A", "N/A"),
                                      tags=('system',))
                return

            # Detectar interfaz de bypass de las rutas y IPs a monitorear
            # La interfaz de bypass es la que NO es VPN (excluir gpd0, tun0, etc.)
            vpn_interfaces = self.manager.get_vpn_interfaces_list()
            bypass_iface = None
            target_ips = []
            iface_count = {}  # Contar cuántas rutas van por cada interfaz

            for route in routes:
                route_info = self.parse_route_technical(route)
                iface = route_info.get('interface')
                dest = route_info['destination'].split('/')[0]

                # Ignorar rutas por interfaz VPN y default
                if iface and iface not in vpn_interfaces and dest and dest != 'default':
                    iface_count[iface] = iface_count.get(iface, 0) + 1
                    target_ips.append(dest)

            # Elegir la interfaz con más rutas de bypass (la más común)
            if iface_count:
                bypass_iface = max(iface_count, key=iface_count.get)
                logger.debug(f"[TCPDUMP] Interfaz bypass detectada: {bypass_iface} ({iface_count[bypass_iface]} rutas)")

            unique_ips = list(set(target_ips)) if target_ips else []

            # Manejar inicio/reinicio/detención automática de tcpdump
            if bypass_iface and unique_ips:
                # Si ya corre, verificar si necesita reinicio (cambio de interfaz o IPs)
                need_restart = False
                if self._tcpdump_running:
                    current_stats = self.manager.get_tcpdump_stats()
                    current_ips = set(current_stats.keys())
                    new_ips = set(unique_ips)
                    # Reiniciar si cambió la interfaz o las IPs
                    if new_ips != current_ips:
                        need_restart = True
                        logger.debug("[TCPDUMP] IPs cambiadas, reiniciando tcpdump...")

                if not self._tcpdump_running or need_restart:
                    try:
                        if need_restart:
                            self.manager.stop_tcpdump_monitor()
                            self._tcpdump_running = False
                        self.manager.start_tcpdump_monitor(bypass_iface, unique_ips)
                        self._tcpdump_running = True
                        logger.info(f"[TCPDUMP] tcpdump en {bypass_iface}: {len(unique_ips)} IPs")
                    except Exception as e:
                        logger.error(f"[TCPDUMP] Error tcpdump: {e}")
            elif self._tcpdump_running:
                # No hay rutas o interfaz, detener tcpdump
                self.manager.stop_tcpdump_monitor()
                self._tcpdump_running = False
                logger.info("[TCPDUMP] tcpdump detenido (sin rutas)")

            # Obtener estadísticas de tráfico (tcpdump en tiempo real o ss como fallback)
            traffic_stats = self.manager.get_tcpdump_stats()
            # Si tcpdump no está corriendo, intentar con el método anterior
            if not traffic_stats:
                traffic_stats = self.manager.get_traffic_stats()

            # Helper para formatear bytes legible (KB/MB)
            def fmt_bytes(b):
                if b == 0:
                    return "-"
                elif b < 1024:
                    return f"{b}B"
                elif b < 1024 * 1024:
                    return f"{b / 1024:.1f}K"
                else:
                    return f"{b / (1024 * 1024):.1f}M"

            # Obtener todas las IPs de dominios activos con sus dominios asociados
            # Usar IPs del daemon si están disponibles, si no resolver por DNS
            domain_ips_map = {}  # ip -> dominio
            for domain, status in domains_with_status:
                if status == 'activo':
                    # Usar IPs del daemon para este dominio (más fiable)
                    if domain in self._domain_ips_from_daemon and self._domain_ips_from_daemon[domain]:
                        ips = self._domain_ips_from_daemon[domain]
                    else:
                        # Fallback: resolver por DNS (si daemon no tiene datos)
                        ips = self.manager.get_domain_ips(domain)
                    for ip in ips:
                        # Normalizar IP (quitar /32 si existe)
                        normalized_ip = ip.split('/')[0] if '/' in ip else ip
                        domain_ips_map[normalized_ip] = domain
            
            # Agrupar rutas por dominio
            domain_routes = {domain: [] for domain, status in domains_with_status if status == 'activo'}
            other_routes = []
            
            for route in routes:
                route_info = self.parse_route_technical(route)
                destination = route_info['destination']
                
                # Normalizar destination para comparar
                dest_normalized = destination.split('/')[0] if '/' in destination else destination
                
                # Buscar si esta IP pertenece a algún dominio
                matched_domain = None
                for ip, domain in domain_ips_map.items():
                    if ip == dest_normalized or destination.startswith(ip):
                        matched_domain = domain
                        break
                
                route_info['ip'] = destination
                if matched_domain:
                    domain_routes[matched_domain].append(route_info)
                else:
                    other_routes.append(route_info)
            
            # Mostrar rutas agrupadas por dominio
            domain_count = 0
            for i, (domain, route_list) in enumerate(domain_routes.items()):
                if not route_list:
                    continue
                    
                domain_count += 1
                # Determinar colores alternados
                alt_tag = 'alt1' if domain_count % 2 == 1 else 'alt2'
                
                # Nodo padre: dominio
                # Calcular estadísticas de tráfico totales para este dominio (inbound/outbound separados)
                domain_total_pkts = 0
                domain_total_in = 0
                domain_total_out = 0
                for r in route_list:
                    ip_norm = r['ip'].split('/')[0] if '/' in r['ip'] else r['ip']
                    stats = traffic_stats.get(ip_norm, {})
                    domain_total_pkts += stats.get('pkts_in', 0) + stats.get('pkts_out', 0)
                    domain_total_in += stats.get('bytes_in', 0)
                    domain_total_out += stats.get('bytes_out', 0)

                pkts_str = f"{domain_total_pkts}" if domain_total_pkts > 0 else "-"
                # Down = bytes_out (servidor envía = tú descargas)
                # Up = bytes_in (servidor recibe = tú subes)
                down_str = fmt_bytes(domain_total_out)
                up_str = fmt_bytes(domain_total_in)
                domain_node = self.routes_tree.insert('', 'end',
                                                     text=domain,
                                                     values=(f"{len(route_list)} rutas", "Activo", pkts_str, down_str, up_str, "Bypass", "N/A"),
                                                     tags=('domain', alt_tag))

                # Nodos hijos: cada ruta con detalles técnicos
                for j, route_info in enumerate(route_list):
                    route_tag = f'route_{alt_tag}'
                    self.routes_tree.tag_configure(route_tag,
                                                 background='#2b2b2b' if j % 2 == 0 else '#333333',
                                                 foreground='#81C784',
                                                 font=('Consolas', 10))

                    # Obtener estadísticas para esta IP específica (inbound/outbound)
                    ip_norm = route_info['ip'].split('/')[0] if '/' in route_info['ip'] else route_info['ip']
                    stats = traffic_stats.get(ip_norm, {})
                    ip_pkts = stats.get('pkts_in', 0) + stats.get('pkts_out', 0)
                    ip_in = stats.get('bytes_in', 0)
                    ip_out = stats.get('bytes_out', 0)

                    ip_pkts_str = f"{ip_pkts}" if ip_pkts > 0 else "-"
                    # Down = out (servidor envía), Up = in (servidor recibe)
                    ip_down_str = fmt_bytes(ip_out)
                    ip_up_str = fmt_bytes(ip_in)

                    self.routes_tree.insert(domain_node, 'end',
                                          text=f"  {route_info['ip']}",
                                          values=(
                                              route_info['gateway'],
                                              route_info['interface'],
                                              ip_pkts_str,
                                              ip_down_str,
                                              ip_up_str,
                                              route_info['protocol'],
                                              route_info['metric']
                                          ),
                                          tags=(route_tag,))
            
            # Mostrar "Otras rutas" si hay IPs no asociadas a dominios
            if other_routes:
                domain_count += 1
                alt_tag = 'alt1' if domain_count % 2 == 1 else 'alt2'
                
                # Calcular estadísticas totales para otras rutas (inbound/outbound)
                other_total_pkts = 0
                other_total_in = 0
                other_total_out = 0
                for r in other_routes:
                    ip_norm = r['ip'].split('/')[0] if '/' in r['ip'] else r['ip']
                    stats = traffic_stats.get(ip_norm, {})
                    other_total_pkts += stats.get('pkts_in', 0) + stats.get('pkts_out', 0)
                    other_total_in += stats.get('bytes_in', 0)
                    other_total_out += stats.get('bytes_out', 0)

                other_pkts_str = f"{other_total_pkts}" if other_total_pkts > 0 else "-"
                # Down = out, Up = in
                other_down_str = fmt_bytes(other_total_out)
                other_up_str = fmt_bytes(other_total_in)

                # Nodo padre: Otras rutas
                other_node = self.routes_tree.insert('', 'end',
                                                   text="Otras rutas",
                                                   values=(f"{len(other_routes)} rutas", "Desconocido", other_pkts_str, other_down_str, other_up_str, "Bypass", "N/A"),
                                                   tags=('system', alt_tag))

                # Nodos hijos: cada ruta no asociada
                for j, route_info in enumerate(other_routes):
                    route_tag = f'other_{alt_tag}'
                    self.routes_tree.tag_configure(route_tag,
                                                 background='#2b2b2b' if j % 2 == 0 else '#333333',
                                                 foreground='#FF9800',
                                                 font=('Consolas', 10))

                    # Estadísticas para esta IP (inbound/outbound)
                    ip_norm = route_info['ip'].split('/')[0] if '/' in route_info['ip'] else route_info['ip']
                    stats = traffic_stats.get(ip_norm, {})
                    ip_pkts = stats.get('pkts_in', 0) + stats.get('pkts_out', 0)
                    ip_in = stats.get('bytes_in', 0)
                    ip_out = stats.get('bytes_out', 0)

                    ip_pkts_str = f"{ip_pkts}" if ip_pkts > 0 else "-"
                    # Down = out, Up = in
                    ip_down_str = fmt_bytes(ip_out)
                    ip_up_str = fmt_bytes(ip_in)

                    self.routes_tree.insert(other_node, 'end',
                                          text=f"  {route_info['ip']}",
                                          values=(
                                              route_info['gateway'],
                                              route_info['interface'],
                                              ip_pkts_str,
                                              ip_down_str,
                                              ip_up_str,
                                              route_info['protocol'],
                                              route_info['metric']
                                          ),
                                          tags=(route_tag,))
            
            # Expandir todos los nodos para mostrar las rutas
            for domain_node in self.routes_tree.get_children():
                self.routes_tree.item(domain_node, open=True)
                
        except Exception as e:
            # Limpiar árbol y mostrar error
            logger.error(f"[ROUTES] ERROR refresh_routes: {e}")
            import traceback
            traceback.print_exc()
            for item in self.routes_tree.get_children():
                self.routes_tree.delete(item)
            self.routes_tree.insert('', 'end', text=f"Error al obtener rutas: {str(e)[:30]}",
                                  values=("Error", "N/A", "N/A", "N/A", "N/A", "N/A"),
                                  tags=('system',))
    
    def remove_domain(self):
        """Elimina el dominio seleccionado"""
        selection = self.domain_tree.selection()
        if not selection:
            logger.warning("[DOMAINS] Por favor seleccione un dominio para eliminar")
            return
        
        try:
            # Obtener el dominio seleccionado
            item = selection[0]
            domain_text = self.domain_tree.item(item)['text']
            
            # Extraer el dominio del texto
            domain = domain_text.strip()
            
            # Eliminar el dominio
            self.manager.remove_domain(domain)
            self.refresh_domains()
            self.refresh_routes()
            self._notify_daemon_domains_changed()
            logger.info(f"[DOMAINS] Dominio {domain} eliminado correctamente")
            
        except Exception as e:
            logger.error(f"[DOMAINS] No se pudo eliminar el dominio: {e}")

    def _check_domains_file_permissions(self):
        """Verifica si tenemos permisos para leer/escribir el archivo de dominios"""
        try:
            domains_file = DOMAINS_FILE
            # Intentar leer el archivo
            with open(domains_file, 'r') as f:
                f.read(1)  # Solo verificar acceso
            
            # Intentar escribir en un archivo temporal en el mismo directorio
            import tempfile
            domains_dir = os.path.dirname(domains_file)
            test_file = os.path.join(domains_dir, ".permission_test")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            return True
        except (PermissionError, OSError):
            return False
    
    def _request_sudo_for_domains(self):
        """Solicita permisos de sudo para el archivo de dominios (ahora en directorio del proyecto)"""
        try:
            domains_dir = os.path.dirname(DOMAINS_FILE)

            # El directorio del proyecto debería tener permisos del usuario
            # Solo necesitamos asegurar que exista
            if domains_dir and not os.path.exists(domains_dir):
                os.makedirs(domains_dir, exist_ok=True)

            return True
        except (PermissionError, OSError) as e:
            logger.error(f"[PERMS] Error con permisos del directorio: {e}")
            return False
        except Exception as e:
            logger.error(f"[PERMS] Error inesperado: {e}")
            return False
    
    def _notify_daemon_domains_changed(self) -> None:
        """Notifica al daemon que los dominios han cambiado"""
        logger.info("[NOTIFY] Intentando notificar al daemon sobre cambio de dominios...")

        # Verificar si el daemon está corriendo primero
        if not self.daemon_controller.is_running():
            logger.warning("[NOTIFY] Daemon no está corriendo - mostrando alerta al usuario")
            messagebox.showwarning(
                "Daemon Inactivo",
                "El daemon no está corriendo.\n\n"
                "Los cambios se han guardado en domains.yml, pero las rutas\n"
                "no se aplicarán hasta que inicies el daemon.\n\n"
                "Usa el botón '▶️ Iniciar' en el menú de control del daemon."
            )
            return

        if self.daemon_controller.notify_reload():
            logger.info("[NOTIFY] Notificación enviada al daemon exitosamente")
        else:
            logger.warning("[NOTIFY] No se pudo notificar al daemon")
    
    # === GESTIÓN DEL DAEMON (delegado a DaemonController) ===

    def check_daemon_status(self) -> None:
        """Verifica el estado del daemon y actualiza la interfaz"""
        try:
            is_running = self.daemon_controller.is_running()
            self._update_daemon_ui(is_running)
            if not is_running and self._domain_ips_from_daemon:
                self._domain_ips_from_daemon = {}
                self.refresh_domains()
        except Exception as e:
            self.daemon_status_label.config(text=f"❌ Error: {str(e)}", foreground='#FF9800')

    def restart_daemon(self) -> None:
        """Reinicia el daemon (usa pkexec si es servicio systemd)"""
        try:
            # Mostrar indicador de carga
            self.restart_daemon_btn.config(state='disabled', text='Reiniciando...')
            self.daemon_status_label.config(text='Reiniciando...', foreground='yellow')
            self.root.update()

            # Ejecutar reinicio (con delay para UI)
            self.root.after(100, self._do_restart_daemon)

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo reiniciar el daemon: {str(e)}")
            self.check_daemon_status()

    def _do_restart_daemon(self) -> None:
        """Ejecuta el reinicio del daemon (separado para permitir UI update)"""
        try:
            if self.daemon_controller.uses_systemd():
                logger.info("[DAEMON] Reiniciando via systemctl con pkexec...")
            result = self.daemon_controller.restart()
            if result:
                logger.info("[DAEMON] Reiniciado correctamente")
            else:
                logger.error("[DAEMON] Falló al reiniciar")
        except Exception as e:
            logger.error(f"[DAEMON] Error reiniciando daemon: {e}")
        finally:
            # Restaurar botón
            self.restart_daemon_btn.config(state='normal', text='🔄 Reiniciar')
            self.check_daemon_status()
    
    def parse_route_technical(self, route_string: str) -> dict:
        """Parsea una ruta para extraer información técnica detallada (delegado a RouteParser)"""
        return RouteParser.parse(route_string)

def main():
    """Función principal"""
    # Verificar dependencias mínimas de la UI (solo python3-yaml)
    try:
        import yaml
    except ImportError:
        logger.error("[INIT] Falta python3-yaml. Ejecute: python3 main.py")
        sys.exit(1)

    # Crear y ejecutar interfaz
    root = tk.Tk()
    app = VPNBypassGUI(root)
    
    # Actualizar estado del daemon periódicamente (las rutas se refrescan en update_vpn_status)
    def update_status():
        try:
            app.check_daemon_status()
        except:
            pass
        root.after(1000, update_status)  # Cada 1 segundo

    root.after(1000, update_status)  # Primer actualización después de 1 segundo
    root.mainloop()

if __name__ == "__main__":
    main()
