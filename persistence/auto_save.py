"""
Loop de guardado automático cada X minutos.
"""

import time
import threading
from persistence.state import OpenMuseStateManager


def start_auto_save(manager: OpenMuseStateManager, interval_minutes: int = 5):
    """Inicia un hilo daemon que guarda el estado periódicamente."""

    def loop():
        while True:
            time.sleep(interval_minutes * 60)
            try:
                manager.save(reason=f"auto cada {interval_minutes} min")
            except Exception as e:
                print(f"Error en auto-save: {e}")

    thread = threading.Thread(target=loop, daemon=True, name="OpenMuseAutoSave")
    thread.start()
    print(f"Auto-save iniciado (cada {interval_minutes} minutos)")
    return thread
