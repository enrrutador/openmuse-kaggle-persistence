"""
Loop de guardado automático cada X minutos.
"""

from __future__ import annotations

import time
import threading
from typing import Optional

from persistence.state import OpenMuseStateManager


def start_auto_save(
    manager: OpenMuseStateManager,
    interval_minutes: int = 5,
) -> threading.Thread:
    """Inicia un hilo daemon que guarda el estado periódicamente."""

    def loop():
        while True:
            time.sleep(interval_minutes * 60)
            try:
                manager.save(reason=f"auto cada {interval_minutes} min")
            except Exception as e:
                print(f"[AutoSave] Error: {e}")

    thread = threading.Thread(
        target=loop,
        daemon=True,
        name="OpenMuseAutoSave",
    )
    thread.start()
    print(f"Auto-save iniciado (cada {interval_minutes} minutos)")
    return thread
