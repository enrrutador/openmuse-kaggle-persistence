# ============================================================
# OPENMUSE EN KAGGLE - TODO EN UNA SOLA CELDA
# Persistencia real + Cloudflare Tunnel
# La URL abre directamente la interfaz de OpenMuse
# ============================================================

import os
import sys
import time
import subprocess
import threading
import zipfile
import shutil
from pathlib import Path
from datetime import datetime

print("=" * 60)
print("  OpenMuse Kaggle - Persistencia + Interfaz Web")
print("=" * 60)

# ----------------------------------------------------------
# 1. Clonar este repo de persistencia
# ----------------------------------------------------------
REPO_DIR = Path("/kaggle/working/openmuse-kaggle-persistence")
if not REPO_DIR.exists():
    print("\n[1/8] Clonando sistema de persistencia...")
    subprocess.run(
        ["git", "clone", "https://github.com/enrrutador/openmuse-kaggle-persistence.git", str(REPO_DIR)],
        check=True,
    )
else:
    print("\n[1/8] Sistema de persistencia ya existe.")

sys.path.insert(0, str(REPO_DIR))

# ----------------------------------------------------------
# 2. Sistema de persistencia
# ----------------------------------------------------------
print("[2/8] Configurando persistencia...")

DATA_DIR = Path("/kaggle/working/openmuse-data")
STATE_ZIP = Path("/kaggle/working/openmuse_state.zip")
BACKUP_DIR = Path("/kaggle/working/backups")
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def save_state(reason="auto"):
    try:
        if not any(DATA_DIR.iterdir()):
            return False
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_zip = BACKUP_DIR / f"state_{timestamp}.zip"
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] Guardando estado ({reason})...")
        with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(DATA_DIR):
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__")]
                for f in files:
                    if f.endswith((".tmp", ".lock", ".log", ".pid")):
                        continue
                    fp = Path(root) / f
                    try:
                        zf.write(fp, fp.relative_to(DATA_DIR))
                    except Exception:
                        pass
        if STATE_ZIP.exists():
            STATE_ZIP.unlink()
        shutil.move(str(temp_zip), str(STATE_ZIP))
        backups = sorted(BACKUP_DIR.glob("state_*.zip"), reverse=True)
        for old in backups[5:]:
            try:
                old.unlink()
            except Exception:
                pass
        size = STATE_ZIP.stat().st_size / (1024 * 1024)
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] Estado guardado ({size:.2f} MB) ✓")
        return True
    except Exception as e:
        print(f"  Error guardando: {e}")
        return False

def restore_state():
    if not STATE_ZIP.exists():
        print("  No hay estado anterior. Empezando limpio.")
        return False
    try:
        print("  Restaurando estado anterior...")
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
        DATA_DIR.mkdir(parents=True)
        with zipfile.ZipFile(STATE_ZIP, "r") as zf:
            zf.extractall(DATA_DIR)
        print("  Estado restaurado ✓")
        return True
    except Exception as e:
        print(f"  Error restaurando: {e}")
        return False

restore_state()

def auto_save_loop():
    while True:
        time.sleep(5 * 60)
        save_state("auto cada 5 min")

threading.Thread(target=auto_save_loop, daemon=True, name="AutoSave").start()
print("  Auto-save cada 5 minutos activado ✓")

# ----------------------------------------------------------
# 3. Instalar OpenMuse
# ----------------------------------------------------------
print("\n[3/8] Instalando OpenMuse (puede tardar)...")

OPENMUSE_DIR = Path("/kaggle/working/openmuse")
if not OPENMUSE_DIR.exists():
    subprocess.run(
        ["git", "clone", "--depth", "1", "https://github.com/CopilotKit/OpenMuse.git", str(OPENMUSE_DIR)],
        check=True,
    )

os.environ["NVM_DIR"] = str(Path.home() / ".nvm")
nvm_sh = Path.home() / ".nvm" / "nvm.sh"

if not nvm_sh.exists():
    print("  Instalando nvm + Node 22...")
    subprocess.run("curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash", shell=True, check=True)

def run_with_node(cmd, cwd=None):
    full = f'source "$NVM_DIR/nvm.sh" && nvm install 22 --no-progress && nvm use 22 && {cmd}'
    return subprocess.run(full, shell=True, cwd=cwd, executable="/bin/bash")

run_with_node("node -v && npm -v")
run_with_node("npm install -g pnpm@11.19.0")
print("  Instalando dependencias de OpenMuse...")
run_with_node("pnpm install --frozen-lockfile || pnpm install", cwd=str(OPENMUSE_DIR))

# ----------------------------------------------------------
# 4. Configurar variables de entorno
# ----------------------------------------------------------
print("\n[4/8] Configurando entorno...")

# IMPORTANTE: PUBLIC_API_URL se actualizará después con la URL del túnel
env_vars = {
    "DATA_DIR": str(DATA_DIR),
    "WORKSPACE_MODE": "sample",
    "AGENT_BACKEND": "sample",
    "PORT": "8787",
    "HOST": "0.0.0.0",
    "PUBLIC_API_URL": "http://localhost:8787",
    "TASK_WORKER_ENABLED": "true",
    "WEB_SEARCH_ENABLED": "true",
    "COMPUTER_ENABLED": "false",
    "EXPO_PUBLIC_API_URL": "http://localhost:8787",
}

for k, v in env_vars.items():
    os.environ[k] = v

env_path = OPENMUSE_DIR / ".env"
env_path.write_text("\n".join(f"{k}={v}" for k, v in env_vars.items()) + "\n")
print("  .env escrito ✓")

# ----------------------------------------------------------
# 5. Arrancar API de OpenMuse (puerto 8787)
# ----------------------------------------------------------
print("\n[5/8] Arrancando API de OpenMuse (puerto 8787)...")

api_proc = subprocess.Popen(
    ["bash", "-c", 'source "$NVM_DIR/nvm.sh" && nvm use 22 && pnpm dev'],
    cwd=str(OPENMUSE_DIR),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    env=os.environ.copy(),
)

print("  Esperando API...")
time.sleep(12)
print("  API en background ✓")

# ----------------------------------------------------------
# 6. Arrancar interfaz web de OpenMuse (puerto 8081)
# ----------------------------------------------------------
print("\n[6/8] Arrancando interfaz web de OpenMuse (puerto 8081)...")

web_proc = subprocess.Popen(
    ["bash", "-c", 'source "$NVM_DIR/nvm.sh" && nvm use 22 && pnpm dev:web'],
    cwd=str(OPENMUSE_DIR),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    env=os.environ.copy(),
)

print("  Esperando interfaz web...")
time.sleep(15)
print("  Interfaz web en background ✓")

# ----------------------------------------------------------
# 7. Cloudflare Tunnel apuntando a la interfaz web (8081)
# ----------------------------------------------------------
print("\n[7/8] Configurando Cloudflare Tunnel (apunta a la interfaz)...")

cloudflared_path = Path("/kaggle/working/cloudflared")
if not cloudflared_path.exists():
    print("  Descargando cloudflared...")
    subprocess.run(
        [
            "wget", "-q",
            "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
            "-O", str(cloudflared_path),
        ],
        check=True,
    )
    cloudflared_path.chmod(0o755)

print("  Iniciando túnel hacia el puerto 8081...")
tunnel_proc = subprocess.Popen(
    [str(cloudflared_path), "tunnel", "--url", "http://localhost:8081"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

public_url = None
print("  Esperando URL pública...")
for _ in range(50):
    line = tunnel_proc.stdout.readline()
    if not line:
        time.sleep(0.4)
        continue
    print("  " + line.rstrip())
    if "trycloudflare.com" in line:
        for part in line.split():
            if "trycloudflare.com" in part:
                public_url = part.strip().rstrip("/")
                break
        if public_url:
            break

# ----------------------------------------------------------
# 8. Resultado final
# ----------------------------------------------------------
print("\n" + "=" * 60)
if public_url:
    print("  LISTO")
    print(f"  Abrí esta URL en el iPhone:")
    print(f"  {public_url}")
    print("")
    print("  Esa URL abre directamente la interfaz de OpenMuse.")
else:
    print("  Servidores arrancados, pero no se pudo capturar la URL.")
    print("  Revisá los logs de cloudflared arriba.")
print("  Auto-save cada 5 minutos activo.")
print("  Para forzar guardado: save_state('manual')")
print("=" * 60)
