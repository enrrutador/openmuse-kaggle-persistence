"""
Sistema de persistencia de estado para OpenMuse en Kaggle.
Guarda y restaura el directorio de datos de OpenMuse.
"""

import os
import time
import zipfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional


class OpenMuseStateManager:
    def __init__(
        self,
        data_dir: str = "/kaggle/working/openmuse-data",
        state_zip: str = "/kaggle/working/openmuse_state.zip",
        backup_dir: str = "/kaggle/working/backups",
        max_backups: int = 3,
    ):
        self.data_dir = Path(data_dir)
        self.state_zip = Path(state_zip)
        self.backup_dir = Path(backup_dir)
        self.max_backups = max_backups

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def save(self, reason: str = "manual") -> bool:
        """Guarda el estado actual en un zip."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_zip = self.backup_dir / f"openmuse_state_{timestamp}.zip"

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Guardando estado ({reason})...")

            with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.data_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(self.data_dir)
                        zipf.write(file_path, arcname)

            # Reemplazar el estado principal
            if self.state_zip.exists():
                self.state_zip.unlink()
            shutil.copy(temp_zip, self.state_zip)

            # Mantener solo los últimos N backups
            backups = sorted(self.backup_dir.glob("openmuse_state_*.zip"), reverse=True)
            for old in backups[self.max_backups:]:
                old.unlink()

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Estado guardado correctamente ✓")
            return True
        except Exception as e:
            print(f"Error guardando estado: {e}")
            return False

    def restore(self) -> bool:
        """Restaura el estado anterior si existe."""
        if not self.state_zip.exists():
            print("No se encontró estado anterior. Empezando limpio.")
            return False

        try:
            print("Restaurando estado anterior...")

            if self.data_dir.exists():
                shutil.rmtree(self.data_dir)
            self.data_dir.mkdir(parents=True)

            with zipfile.ZipFile(self.state_zip, "r") as zipf:
                zipf.extractall(self.data_dir)

            print("Estado restaurado correctamente ✓")
            return True
        except Exception as e:
            print(f"Error restaurando estado: {e}")
            return False

    def get_data_dir(self) -> Path:
        return self.data_dir
