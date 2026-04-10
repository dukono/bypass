#!/usr/bin/env python3
"""
TrafficMonitor - Monitoreo periódico de tráfico
"""
import time
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class TrafficMonitor:
    """Monitorea el tráfico periódicamente para actualizar estadísticas"""

    DEFAULT_INTERVAL = 5000  # ms

    def __init__(self, callback: Callable[[], None], interval_ms: int = DEFAULT_INTERVAL):
        self.callback = callback
        self.interval_ms = interval_ms
        self._running = False
        self._tk_root = None  # Referencia opcional para tkinter.after()
        self._timer_id: Optional[int] = None

    def start(self, tk_root=None) -> None:
        """Inicia el monitoreo. Si tk_root se proporciona, usa tkinter.after()"""
        if self._running:
            return

        self._running = True
        self._tk_root = tk_root

        if tk_root:
            # Usar tkinter.after() para integración con UI
            self._schedule_tkinter()
            logger.info(f"[TRAFFIC] Monitor iniciado con tkinter (intervalo: {self.interval_ms}ms)")
        else:
            # Modo standalone con threading
            self._start_threading()
            logger.info(f"[TRAFFIC] Monitor iniciado con threading (intervalo: {self.interval_ms}ms)")

    def stop(self) -> None:
        """Detiene el monitoreo"""
        self._running = False
        if self._timer_id and self._tk_root:
            try:
                self._tk_root.after_cancel(self._timer_id)
            except Exception as e:
                logger.debug(f"[TRAFFIC] Error cancelando timer: {e}")
        self._timer_id = None
        logger.info("[TRAFFIC] Monitor detenido")

    def is_running(self) -> bool:
        """Retorna True si el monitor está corriendo"""
        return self._running

    def set_interval(self, interval_ms: int) -> None:
        """Cambia el intervalo de monitoreo"""
        was_running = self._running
        if was_running:
            self.stop()
        self.interval_ms = interval_ms
        if was_running:
            self.start(self._tk_root)

    def _schedule_tkinter(self) -> None:
        """Programa la siguiente ejecución usando tkinter.after()"""
        if not self._running or not self._tk_root:
            return

        def execute_and_reschedule():
            if not self._running:
                return
            try:
                self.callback()
            except Exception as e:
                logger.error(f"[TRAFFIC] Error en callback: {e}")
            # Reprogramar siguiente ejecución
            self._schedule_tkinter()

        self._timer_id = self._tk_root.after(self.interval_ms, execute_and_reschedule)

    def _start_threading(self) -> None:
        """Inicia el monitoreo usando threading (modo standalone)"""
        import threading

        def monitor_loop():
            while self._running:
                try:
                    self.callback()
                except Exception as e:
                    logger.error(f"[TRAFFIC] Error en callback: {e}")
                time.sleep(self.interval_ms / 1000)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
