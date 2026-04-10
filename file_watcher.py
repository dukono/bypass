#!/usr/bin/env python3
"""
FileWatcher - Monitoreo de archivos con polling
"""
import os
import time
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class FileWatcher:
    """Watcher de archivos usando polling periódico"""

    def __init__(self, file_path: str, callback: Callable[[], None]):
        self.file_path = file_path
        self.callback = callback
        self._polling_thread: Optional[threading.Thread] = None
        self._polling_running = False
        self._last_mtime: float = 0

    def start(self) -> bool:
        """Inicia el file watcher con polling"""
        self._start_polling()
        return True

    def stop(self) -> None:
        """Detiene el file watcher"""
        if self._polling_running:
            self._polling_running = False
            if self._polling_thread:
                self._polling_thread.join(timeout=1.0)
            logger.info("[WATCHER] Polling watcher detenido")

    def _start_polling(self) -> None:
        """Inicia el watcher usando polling periódico"""
        self._polling_running = True
        self._last_mtime = self._get_file_mtime()

        self._polling_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._polling_thread.start()
        logger.info(f"[WATCHER] File watcher iniciado (polling 2s) para {self.file_path}")

    def _poll_loop(self) -> None:
        """Loop de polling"""
        while self._polling_running:
            try:
                time.sleep(2)  # Intervalo de polling

                current_mtime = self._get_file_mtime()
                if current_mtime != self._last_mtime:
                    self._last_mtime = current_mtime
                    logger.debug(f"[WATCHER] Cambio detectado por polling")
                    self.callback()
            except Exception as e:
                logger.error(f"[WATCHER] Error en polling: {e}")

    def _get_file_mtime(self) -> float:
        """Obtiene el mtime del archivo, o 0 si no existe"""
        try:
            if os.path.exists(self.file_path):
                return os.path.getmtime(self.file_path)
        except Exception:
            pass
        return 0
