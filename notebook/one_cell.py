# ============================================================
# OPENMUSE EN KAGGLE - TODO EN UNA SOLA CELDA
# Persistencia real + Cloudflare Tunnel
# La URL abre directamente la interfaz de OpenMuse
# ============================================================

import os
import re
import sys
import time
import subprocess
import threading
import zipfile
import shutil
import urllib.request
from pathlib import Path
from datetime import datetime

print("=" * 60)
print("  OpenMuse Kaggle - Persistencia + Interfaz Web")
print("  VERSION: 2026-10-04.5 (si no ves esta version, tu celda tiene codigo viejo pegado)")
print("=" * 60)

URL_RE = re.compile(r"https://[A-Za-z0-9-]+\.trycloudflare\.com")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def clean(s: str) -> str:
    return ANSI_RE.sub("", s).strip()


def wait_for_tunnel_url(proc, timeout=90, label="túnel"):
    """Lee la salida de cloudflared hasta encontrar https://xxx.trycloudflare.com.

    FIX del bug anterior: antes se hacía `if "trycloudflare.com" in line`,
    lo que matcheaba la línea informativa
    "Requesting new quick Tunnel on trycloudflare.com..." y guardaba
    el literal "trycloudflare.com..." como URL. Ahora se exige regex
    https://<subdominio>.trycloudflare.com.
    """
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            print(f"  [WARN] proceso del {label} terminó (exit={proc.poll()})")
            break
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.5)
            continue
        c = clean(line)
        if c:
            print("  " + c)
        m = URL_RE.search(c)
        if m:
            url = m.group(0).rstrip("/")
            # Quita restos tipo "|" o "," que a veces pega cloudflared
            url = url.strip("|, ")
            return url
    return None


def wait_for_http(url, timeout=180, label="servicio"):
    """Espera hasta que url responda 2xx/3xx. Retorna True/False."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if 200 <= r.status < 400:
                    print(f"  {label} responde ✓ ({url} -> {r.status})")
                    return True
        except Exception:
            pass
        time.sleep(3)
    print(f"  [WARN] {label} no respondió en {timeout}s: {url}")
    return False


def drain(proc, prefix):
    """Hilo daemon que imprime logs sin bloquear el pipe."""
    def _run():
        try:
            for line in proc.stdout:
                c = clean(line)
                if c:
                    print(f"  [{prefix}] {c}", flush=True)
        except Exception:
            pass
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def get_cpk_key():
    """Lee CPK_INTELLIGENCE_API_KEY del entorno o del secreto de Kaggle.

    OpenMuse la exige siempre (hasta en modo sample). Sin ella la API
    muere al arrancar con 'OpenMuse requires CPK_INTELLIGENCE_API_KEY'.
    """
    v = os.environ.get("CPK_INTELLIGENCE_API_KEY", "").strip()
    if v:
        return v
    try:
        from kaggle_secrets import UserSecretsClient
        v = UserSecretsClient().get_secret("CPK_INTELLIGENCE_API_KEY") or ""
        if v.strip():
            return v.strip()
    except Exception as e:
        print(f"  (no se pudo leer el secreto de Kaggle: {e})")
    return ""


# ----------------------------------------------------------
# 0. Limpieza de corridas anteriores (mismo kernel, celda re-ejecutada)
# ----------------------------------------------------------
# Sin esto, los procesos viejos siguen ocupando 8787/8081 y la
# re-ejecución "no cambia nada" (los servidores nuevos no levantan).
print("[0/8] Liberando procesos/puertos de corridas anteriores...")
for _port in (8787, 8081):
    try:
        subprocess.run(["fuser", "-k", f"{_port}/tcp"],
                       capture_output=True, timeout=10)
    except Exception:
        pass
try:
    subprocess.run(["pkill", "-f", "cloudflared"],
                   capture_output=True, timeout=10)
except Exception:
    pass
time.sleep(2)
print("  Puertos liberados ✓")


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
    print("\n[1/8] Sistema de persistencia ya existe. Actualizando...")
    try:
        subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--ff-only"], check=True)
        print("  Repo actualizado ✓ (así la celda siempre usa el código corregido)")
    except Exception as e:
        print(f"  [WARN] no se pudo actualizar ({e}), sigo con la copia local.")

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
# 4. Clave CPK + cloudflared + túneles API y WEB (antes de arrancar nada)
# ----------------------------------------------------------
# - OpenMuse exige CPK_INTELLIGENCE_API_KEY hasta en modo sample. Se lee
#   del entorno o del secreto de Kaggle "CPK_INTELLIGENCE_API_KEY".
#   Sin ella la API muere al arrancar: se aborta acá con instrucciones.
# - La web (Expo) incrusta EXPO_PUBLIC_API_URL al arrancar y la API valida
#   CORS contra ALLOWED_ORIGINS al arrancar. Por eso los DOS túneles se
#   crean primero (funcionan aunque el backend aún esté caído) y luego se
#   arranca todo con las URLs públicas ya conocidas.
print("\n[4/8] Verificando clave + preparando túneles...")

cpk_key = get_cpk_key()
if not cpk_key:
    print("\n" + "=" * 60)
    print("  FALTA CPK_INTELLIGENCE_API_KEY — la API no puede arrancar sin ella.")
    print("  Cómo obtenerla (gratis, desde el iPhone, sin laptop ni terminal):")
    print("  1. En Safari abrí https://intelligence.copilotkit.ai y creá tu cuenta")
    print("  2. Creá un proyecto y andá a la página API Keys del proyecto")
    print("  3. Copiá la key que empieza con cpk-...")
    print("  En Kaggle: Add-ons -> Secrets -> Add secret")
    print('    nombre: CPK_INTELLIGENCE_API_KEY, valor: la key. Adjuntá el')
    print("    secreto al notebook y re-ejecutá la celda.")
    print("=" * 60)
    raise SystemExit("Falta CPK_INTELLIGENCE_API_KEY")
print("  CPK_INTELLIGENCE_API_KEY presente ✓ (no se muestra por seguridad)")

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
else:
    print("  cloudflared ya existe ✓")

print("  Iniciando túnel API hacia http://localhost:8787 ...")
api_tunnel = subprocess.Popen(
    [str(cloudflared_path), "tunnel", "--url", "http://localhost:8787"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

print("  Esperando URL pública de la API (hasta 90s)...")
api_url = wait_for_tunnel_url(api_tunnel, timeout=90, label="túnel API")
if api_url:
    print(f"  API pública: {api_url} ✓")
    drain(api_tunnel, "tunnel-api")
else:
    print("  [WARN] no se capturó URL de API, uso fallback localhost.")
    print("  (La web NO funcionará desde el iPhone sin URL pública de API.)")
    api_url = "http://localhost:8787"

print("  Iniciando túnel WEB hacia http://localhost:8081 ...")
web_tunnel = subprocess.Popen(
    [str(cloudflared_path), "tunnel", "--url", "http://localhost:8081"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

print("  Esperando URL pública de la web (hasta 90s)...")
web_url = wait_for_tunnel_url(web_tunnel, timeout=90, label="túnel web")
if web_url:
    print(f"  Web pública: {web_url} ✓")
    drain(web_tunnel, "tunnel-web")
else:
    print("  [WARN] no se capturó URL web.")
    web_url = None

# ----------------------------------------------------------
# 5. Variables de entorno (ya con la URL pública real)
# ----------------------------------------------------------
print("\n[5/8] Configurando entorno...")

# HOST debe ser loopback: en modo sample OpenMuse rechaza 0.0.0.0.
# ALLOWED_ORIGINS debe incluir la URL pública de la WEB (origen cruzado
# desde el iPhone), si no la API responde 403 a la interfaz.
allowed = "http://localhost:8081,http://127.0.0.1:8081"
if web_url:
    allowed += f",{web_url}"
env_vars = {
    "DATA_DIR": str(DATA_DIR),
    "WORKSPACE_MODE": "sample",
    "AGENT_BACKEND": "sample",
    "PORT": "8787",
    "HOST": "127.0.0.1",
    "PUBLIC_API_URL": api_url,
    "ALLOWED_ORIGINS": allowed,
    "CPK_INTELLIGENCE_API_KEY": cpk_key,
    "TASK_WORKER_ENABLED": "true",
    "WEB_SEARCH_ENABLED": "true",
    "COMPUTER_ENABLED": "false",
    "EXPO_PUBLIC_API_URL": api_url,
}

for k, v in env_vars.items():
    os.environ[k] = v

env_path = OPENMUSE_DIR / ".env"
env_path.write_text("\n".join(f"{k}={v}" for k, v in env_vars.items()) + "\n")
print(f"  .env escrito ✓ (PUBLIC_API_URL={api_url})")

# ----------------------------------------------------------
# 6. Arrancar API de OpenMuse (puerto 8787)
# ----------------------------------------------------------
print("\n[6/8] Arrancando API de OpenMuse (puerto 8787)...")

api_proc = subprocess.Popen(
    ["bash", "-c", 'source "$NVM_DIR/nvm.sh" && nvm use 22 && pnpm dev'],
    cwd=str(OPENMUSE_DIR),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    env=os.environ.copy(),
)
drain(api_proc, "api")

if not wait_for_http("http://localhost:8787/api/health", timeout=150, label="API"):
    print("\n" + "=" * 60)
    print("  La API no levantó. Revisá los logs [api] arriba: la causa más")
    print("  común es una CPK_INTELLIGENCE_API_KEY inválida o sin proyecto")
    print("  seleccionado en CopilotKit.")
    print("  Se aborta para no dejar túneles apuntando a nada.")
    print("=" * 60)
    raise SystemExit("API no responde en /api/health")
print("  API en background ✓")

# ----------------------------------------------------------
# 7. Arrancar web (8081) — su túnel ya se creó en [4/8]
# ----------------------------------------------------------
print("\n[7/8] Arrancando interfaz web de OpenMuse (puerto 8081)...")

web_proc = subprocess.Popen(
    ["bash", "-c", 'source "$NVM_DIR/nvm.sh" && nvm use 22 && pnpm dev:web'],
    cwd=str(OPENMUSE_DIR),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    env=os.environ.copy(),
)
drain(web_proc, "web")

if not wait_for_http("http://localhost:8081/", timeout=240, label="Web"):
    print("\n" + "=" * 60)
    print("  La web no levantó. Revisá los logs [web] arriba.")
    print("=" * 60)
    raise SystemExit("Web no responde en puerto 8081")
print("  Interfaz web en background ✓")

# ----------------------------------------------------------
# 8. Resultado final + keep-alive
# ----------------------------------------------------------
print("\n" + "=" * 60)
if web_url:
    print("  LISTO — en el iPhone abrí ESTA (la de la WEB):")
    print(f"  {web_url}")
    print("")
    print("  NO abras la de la API en Safari (da 502/JSON, es solo para la app):")
    print(f"  API: {api_url}")
else:
    print("  Servidores arrancados, pero no se pudo capturar la URL web.")
    print(f"  API pública (por si sirve): {api_url}")
    print("  Revisá los logs [tunnel-web] arriba.")
print("  Auto-save cada 5 minutos activo.")
print("  Para forzar guardado: save_state('manual')")
print("=" * 60)

# Keep-alive: la celda queda viva para que Kaggle no mate los procesos.
# Cada 60s verifica que API/web/túneles sigan vivos.
print("\n[keep-alive] Celda viva. Ctrl+C / Stop para terminar.")
try:
    while True:
        time.sleep(60)
        for name, p in [("api", api_proc), ("web", web_proc),
                        ("tunnel-api", api_tunnel), ("tunnel-web", web_tunnel)]:
            if p.poll() is not None:
                print(f"  [WARN] {name} terminó con exit={p.poll()}")
        save_state("keep-alive cada 60 min (placeholder)") if False else None
except KeyboardInterrupt:
    print("  Keep-alive interrumpido.")
