"""
Sistema de persistencia de estado para OpenMuse en Kaggle.
Guarda y restaura el directorio de datos de OpenMuse de forma robusta.
"""

from __future__ import annotations

import os
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
        max_backups: int = 5,
    ):
        self.data_dir = Path(data_dir)
        self.state_zip = Path(state_zip)
        self.backup_dir = Path(backup_dir)
        self.max_backups = max_backups

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def save(self, reason: str = "manual") -> bool:
        """Guarda el estado actual en un zip de forma segura."""
        try:
            if not any(self.data_dir.iterdir()):
                print(f"[{self._now()}] No hay datos para guardar aún.")
                return False

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_zip = self.backup_dir / f"openmuse_state_{timestamp}.zip"

            print(f"[{self._now()}] Guardando estado ({reason})...")

            with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.data_dir):
                    # Evitar directorios problemáticos
                    dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__")]

                    for file in files:
                        if file.endswith((".tmp", ".lock", ".log", ".pid")):
                            continue
                        file_path = Path(root) / file
                        try:
                            arcname = file_path.relative_to(self.data_dir)
                            zipf.write(file_path, arcname)
                        except Exception:
                            # Si un archivo individual falla, seguimos con el resto
                            continue

            # Reemplazo atómico del estado principal
            if self.state_zip.exists():
                self.state_zip.unlink()
            shutil.move(str(temp_zip), str(self.state_zip))

            self._cleanup_old_backups()

            size_mb = self.state_zip.stat().st_size / (1024 * 1024)
            print(f"[{self._now()}] Estado guardado correctamente ({size_mb:.2f} MB) ✓")
            return True

        except Exception as e:
            print(f"[{self._now()}] Error guardando estado: {e}")
            return False

    def restore(self) -> bool:
        """Restaura el estado anterior si existe."""
        if not self.state_zip.exists():
            print(f"[{self._now()}] No se encontró estado anterior. Empezando limpio.")
            return False

        try:
            print(f"[{self._now()}] Restaurando estado anterior...")

            if self.data_dir.exists():
                shutil.rmtree(self.data_dir)
            self.data_dir.mkdir(parents=True)

            with zipfile.ZipFile(self.state_zip, "r") as zipf:
                zipf.extractall(self.data_dir)

            print(f"[{self._now()}] Estado restaurado correctamente ✓")
            return True

        except Exception as e:
            print(f"[{self._now()}] Error restaurando estado: {e}")
            return False

    def status(self) -> dict:
        """Devuelve información útil del estado actual."""
        info = {
            "data_dir": str(self.data_dir),
            "state_zip_exists": self.state_zip.exists(),
            "data_dir_exists": self.data_dir.exists(),
            "data_dir_size_mb": 0.0,
            "state_zip_size_mb": 0.0,
            "file_count": 0,
        }

        if self.data_dir.exists():
            total = 0
            count = 0
            for root, _, files in os.walk(self.data_dir):
                for f in files:
                    fp = Path(root) / f
                    try:
                        total += fp.stat().st_size
                        count += 1
                    except Exception:
                        pass
            info["data_dir_size_mb"] = round(total / (1024 * 1024), 2)
            info["file_count"] = count

        if self.state_zip.exists():
            info["state_zip_size_mb"] = round(self.state_zip.stat().st_size / (1024 * 1024), 2)

        return info

    def get_data_dir(self) -> Path:
        return self.data_dir

    def exists(self) -> bool:
        return self.state_zip.exists()

    def _cleanup_old_backups(self):
        backups = sorted(self.backup_dir.glob("openmuse_state_*.zip"), reverse=True)
        for old in backups[self.max_backups:]:
            try:
                old.unlink()
            except Exception:
                pass

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%H:%M:%S")
