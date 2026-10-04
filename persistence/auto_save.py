"""
Loop de guardado automático cada X minutos.
"""

import time
import threading
from persistence.state import OpenMuseStateManager


def start_auto_save(manager: OpenMuseStateManager, interval_minutes: int = 5):
    """Inicia un hilo que guarda el estado periódicamente."""

    def loop():
        while True:
            time.sleep(interval_minutes * 60)
            manager.save(reason=f"auto cada {interval_minutes} min")

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    print(f"Auto-save iniciado (cada {interval_minutes} minutos)")
    return thread
