#!/usr/bin/env python3
"""
SetupDialog - UI para verificar e instalar dependencias del sistema
"""
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import logging

logger = logging.getLogger(__name__)


class SetupDialog:
    """Diálogo de configuración para verificar e instalar dependencias"""

    DEPENDENCIES = [
        {'name': 'python3-tk', 'check': ['python3', '-c', 'import tkinter'], 'type': 'apt'},
        {'name': 'dnsutils', 'check': ['dig', '-v'], 'type': 'apt'},
        {'name': 'iproute2', 'check': ['ip', 'route'], 'type': 'apt'},
        # TEMPORAL: para testear la ventana de instalación
        {'name': 'gedit', 'check': ['gedit', '--version'], 'type': 'apt'},
    ]

    def __init__(self, parent=None, auto_mode=False):
        self.parent = parent
        self.auto_mode = auto_mode  # True = sin interacción usuario
        self.results = {}
        self.window = None
        self.tree = None
        self.install_btn = None
        self.status_label = None
        self.auto_install_success = False

    def show(self) -> bool:
        """Muestra el diálogo y retorna True si todas las dependencias están instaladas"""
        self.window = tk.Toplevel(self.parent) if self.parent else tk.Tk()
        self.window.title("Configuración de Dependencias" if not self.auto_mode else "Instalando Dependencias...")
        self.window.geometry("550x400")
        self.window.resizable(False, False)

        # Hacer modal
        if self.parent:
            self.window.transient(self.parent)
            self.window.grab_set()

        self._create_ui()

        # En modo automático, ejecutar todo sin interacción
        if self.auto_mode:
            self.window.after(100, self._auto_run)
        else:
            self._check_all()

        # Centrar ventana
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (550 // 2)
        y = (self.window.winfo_screenheight() // 2) - (400 // 2)
        self.window.geometry(f"+{x}+{y}")

        if not self.parent:
            self.window.mainloop()
            if self.auto_mode:
                return self.auto_install_success
            return all(r['installed'] for r in self.results.values())
        return True

    def _auto_run(self):
        """Ejecuta verificación e instalación automática sin interacción del usuario"""
        self._check_all()
        self.window.update()

        # Verificar si faltan dependencias
        missing = [(name, r) for name, r in self.results.items() if not r['installed']]

        if not missing:
            # Todo OK, cerrar automáticamente
            logger.info("[SETUP_AUTO] Todas las dependencias verificadas. Cerrando...")
            self.auto_install_success = True
            self.window.after(500, self._on_continue)
            return

        # Hay dependencias faltantes, instalar automáticamente
        self.status_label.config(text=f"Instalando {len(missing)} dependencia(s)...", foreground='blue')
        self.window.update()
        logger.info(f"[SETUP_AUTO] Instalando automáticamente: {[n for n,_ in missing]}")

        # Ejecutar instalación sin confirmación
        self._install_missing_auto()

    def _install_missing_auto(self):
        """Instala dependencias faltantes automáticamente (sin preguntar al usuario)"""
        missing = [(name, r) for name, r in self.results.items() if not r['installed']]
        success = []
        failed = []

        for name, info in missing:
            try:
                self.status_label.config(text=f"Instalando {name}...", foreground='blue')
                self.window.update()
                logger.info(f"[SETUP_AUTO] Instalando {name}...")

                if info['type'] == 'apt':
                    result = subprocess.run(
                        ['sudo', 'apt', 'install', '-y', name],
                        capture_output=True, text=True, timeout=120
                    )
                else:
                    continue

                if result.returncode == 0:
                    success.append(name)
                    logger.info(f"[SETUP_AUTO] {name} instalado correctamente")
                else:
                    failed.append(f"{name} (código {result.returncode})")
                    logger.error(f"[SETUP_AUTO] Falló {name}: {result.stderr}")

            except Exception as e:
                failed.append(f"{name} ({str(e)})")
                logger.error(f"[SETUP_AUTO] Error instalando {name}: {e}")

        # Actualizar estado
        self._check_all()

        if failed:
            # Falló algo, quedar abierto mostrando error
            error_details = ", ".join(failed)
            self.status_label.config(text=f"❌ Error instalando: {error_details}", foreground='red')
            logger.error(f"[SETUP_AUTO] Fallos: {failed}")
            self.auto_install_success = False
            # No cerrar, mostrar error al usuario
        else:
            # Todo OK, cerrar automáticamente
            self.status_label.config(text="✅ Instalación completada", foreground='green')
            self.window.update()
            logger.info("[SETUP_AUTO] Instalación completada exitosamente. Cerrando...")
            self.auto_install_success = True
            self.window.after(500, self._on_continue)

    def _create_ui(self):
        """Crea los widgets de la interfaz"""
        # Frame principal
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill='both', expand=True)

        # Título
        title = ttk.Label(main_frame, text="Verificación de Dependencias",
                         font=('Arial', 14, 'bold'))
        title.pack(pady=(0, 10))

        # Descripción
        desc = ttk.Label(main_frame, text="Las siguientes dependencias son necesarias para el funcionamiento correcto:",
                        wraplength=500)
        desc.pack(pady=(0, 15))

        # Treeview para dependencias
        columns = ('dependencia', 'estado', 'tipo')
        self.tree = ttk.Treeview(main_frame, columns=columns, show='headings',
                                 height=6, selectmode='browse')

        self.tree.heading('dependencia', text='Dependencia')
        self.tree.heading('estado', text='Estado')
        self.tree.heading('tipo', text='Tipo')

        self.tree.column('dependencia', width=200)
        self.tree.column('estado', width=150)
        self.tree.column('tipo', width=100)

        # Scrollbar
        scrollbar = ttk.Scrollbar(main_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Status label
        self.status_label = ttk.Label(main_frame, text="Verificando...", foreground='gray')
        self.status_label.pack(pady=(15, 5))

        # Frame de botones (diferente según modo)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=(10, 0))

        if self.auto_mode:
            # Modo automático: solo botón de cerrar (para cuando haya errores)
            self.close_btn = ttk.Button(btn_frame, text="Cerrar",
                                       command=self._on_continue, state='disabled')
            self.close_btn.pack(side='left', padx=5)
        else:
            # Modo manual: todos los botones de control
            # Botón instalar
            self.install_btn = ttk.Button(btn_frame, text="Instalar Faltantes",
                                          command=self._install_missing, state='disabled')
            self.install_btn.pack(side='left', padx=5)

            # Botón continuar (solo si todo OK)
            self.continue_btn = ttk.Button(btn_frame, text="Continuar",
                                           command=self._on_continue, state='disabled')
            self.continue_btn.pack(side='left', padx=5)

            # Botón cancelar
            ttk.Button(btn_frame, text="Cancelar",
                       command=self._on_cancel).pack(side='left', padx=5)

            # Botón recheck
            ttk.Button(btn_frame, text="Verificar Nuevamente",
                       command=self._check_all).pack(side='left', padx=5)

    def _check_all(self, auto_continue=False):
        """Verifica todas las dependencias"""
        self.status_label.config(text="Verificando dependencias...", foreground='blue')
        self.window.update()

        # Limpiar tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.results = {}

        for dep in self.DEPENDENCIES:
            name = dep['name']
            check_cmd = dep['check']
            dep_type = dep['type']

            installed = self._check_dependency(check_cmd, name)
            self.results[name] = {
                'installed': installed,
                'type': dep_type,
                'check_cmd': check_cmd
            }

            status = "✅ Instalada" if installed else "❌ No instalada"
            self.tree.insert('', 'end', values=(name, status, dep_type))

        self._update_status()
        self.window.update()

        # Log de resultados
        installed_count = sum(1 for r in self.results.values() if r['installed'])
        logger.info(f"[SETUP] Verificación: {installed_count}/{len(self.DEPENDENCIES)} dependencias instaladas")
        for name, r in self.results.items():
            status = "✅" if r['installed'] else "❌"
            logger.info(f"[SETUP]   {status} {name}")

        # Auto-continuar si todo está instalado y se solicita
        if auto_continue and all(r['installed'] for r in self.results.values()):
            self.window.after(500, self._on_continue)

    def _check_dependency(self, check_cmd: list, name: str = None) -> bool:
        """Verifica si una dependencia está instalada"""
        try:
            result = subprocess.run(check_cmd, capture_output=True, timeout=5)
            installed = result.returncode == 0
            if name and not installed:
                logger.debug(f"[SETUP] Check falló para {name}: cmd={check_cmd}, rc={result.returncode}")
            return installed
        except Exception as e:
            if name:
                logger.debug(f"[SETUP] Check excepción para {name}: {e}")
            return False

    def _update_status(self):
        """Actualiza el estado general y botones"""
        all_installed = all(r['installed'] for r in self.results.values())
        any_missing = any(not r['installed'] for r in self.results.values())

        if self.auto_mode:
            # Modo automático: solo habilitar botón cerrar si hay error (no todo instalado)
            if hasattr(self, 'close_btn'):
                self.close_btn.config(state='normal' if any_missing else 'disabled')
            return

        if all_installed:
            self.status_label.config(text="✅ Todas las dependencias están instaladas",
                                    foreground='green')
            self.install_btn.config(state='disabled')
            self.continue_btn.config(state='normal')
        else:
            missing = [name for name, r in self.results.items() if not r['installed']]
            self.status_label.config(
                text=f"⚠️ Faltan {len(missing)} dependencia(s): {', '.join(missing)}",
                foreground='orange'
            )
            self.install_btn.config(state='normal' if any_missing else 'disabled')
            self.continue_btn.config(state='disabled')

    def _install_missing(self):
        """Instala las dependencias faltantes"""
        missing = [(name, r) for name, r in self.results.items() if not r['installed']]

        if not missing:
            messagebox.showinfo("Info", "No hay dependencias faltantes")
            return

        # Confirmar
        names = ', '.join([name for name, _ in missing])
        if not messagebox.askyesno("Confirmar Instalación",
                                   f"Se instalarán las siguientes dependencias:\n{names}\n\n"
                                   f"Esto requiere privilegios de administrador (sudo).\n"
                                   f"¿Continuar?"):
            return

        self.status_label.config(text="Instalando...", foreground='blue')
        self.install_btn.config(state='disabled')
        self.window.update()

        logger.info(f"[SETUP] Iniciando instalación de {len(missing)} dependencias: {[n for n,_ in missing]}")

        success = []
        failed = []

        for name, info in missing:
            try:
                if info['type'] == 'apt':
                    result = subprocess.run(
                        ['sudo', 'apt', 'install', '-y', name],
                        capture_output=True, text=True, timeout=120
                    )
                elif info['type'] == 'pip':
                    package_name = name.replace(' (pip)', '')
                    python_cmd = self.SYSTEM_PYTHON
                    logger.info(f"[SETUP] Instalando {package_name} con {python_cmd}")
                    result = subprocess.run(
                        [python_cmd, '-m', 'pip', 'install', '--user', package_name],
                        capture_output=True, text=True, timeout=60
                    )
                    logger.info(f"[SETUP] Código retorno pip: {result.returncode}")
                else:
                    continue

                if result.returncode == 0:
                    success.append(name)
                    logger.info(f"[SETUP] Instalado: {name}")
                    if info['type'] == 'pip':
                        logger.info(f"[SETUP] Salida pip: {result.stdout}")
                else:
                    error_msg = result.stderr.strip() if result.stderr else "Sin mensaje de error"
                    failed.append(f"{name} (código {result.returncode})")
                    logger.error(f"[SETUP] Falló: {name} - {error_msg}")
                    logger.error(f"[SETUP] stdout: {result.stdout}")

            except Exception as e:
                failed.append(f"{name} ({str(e)})")
                logger.error(f"[SETUP] Error instalando {name}: {e}")

        # Recheck después de instalar (auto_continue=True si todo se instaló)
        all_installed = len(success) > 0 and len(failed) == 0 and len(success) == len(missing)
        self._check_all(auto_continue=all_installed)

        # Mostrar resultado solo si hubo fallos o no se auto-continuó
        if failed:
            # Recopilar errores detallados para mostrar al usuario
            error_details = "\n".join([f"  • {f}" for f in failed])
            messagebox.showwarning("Resultado Parcial",
                                 f"✅ Instalados: {len(success)}\n"
                                 f"❌ Fallidos:\n{error_details}\n\n"
                                 f"Revisa el log para más detalles.")
        elif success and not all_installed:
            messagebox.showinfo("Éxito",
                               f"Se instalaron {len(success)} dependencia(s) correctamente.")

    def _on_continue(self):
        """Cierra el diálogo continuando"""
        self.window.destroy()

    def _on_cancel(self):
        """Cierra el diálogo cancelando"""
        if messagebox.askyesno("Confirmar",
                               "Algunas funciones pueden no funcionar sin las dependencias.\n"
                               "¿Continuar de todas formas?"):
            self.window.destroy()
            if not self.parent:
                raise SystemExit(1)


def check_and_show_setup(parent=None, auto_check=True) -> bool:
    """
    Verifica dependencias y muestra el diálogo si faltan.
    Retorna True si todas están instaladas (o usuario quiere continuar).
    """
    dialog = SetupDialog(parent)

    # Verificación rápida sin UI
    if auto_check:
        all_ok = True
        for dep in SetupDialog.DEPENDENCIES:
            try:
                result = subprocess.run(dep['check'], capture_output=True, timeout=5)
                if result.returncode != 0:
                    all_ok = False
                    break
            except Exception:
                all_ok = False
                break

        if all_ok:
            logger.info("[SETUP] Todas las dependencias verificadas (sin UI)")
            return True

    # Mostrar UI si faltan dependencias
    return dialog.show()


if __name__ == "__main__":
    # Test standalone
    logging.basicConfig(level=logging.INFO)
    result = check_and_show_setup(auto_check=False)
    print(f"Resultado: {result}")
