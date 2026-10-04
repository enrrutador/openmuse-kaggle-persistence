# ============================================================
# OPENMUSE EN KAGGLE - TODO EN UNA SOLA CELDA
# Persistencia real + Cloudflare Tunnel
# VERSION DIRECT: servicios primero → túneles después
# (sin connection refused en el arranque)
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

VERSION = "2026-10-04.10-direct"

print("=" * 60)
print("  OpenMuse Kaggle - Persistencia + Interfaz Web")
print(f"  VERSION: {VERSION}")
print("  (si no ves esta version, tu celda tiene codigo viejo pegado)")
print("=" * 60)

URL_RE = re.compile(r"https://[A-Za-z0-9-]+\.trycloudflare\.com")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def clean(s: str) -> str:
    return ANSI_RE.sub("", s).strip()


def wait_for_tunnel_url(proc, timeout=90, label="túnel"):
    """Lee la salida de cloudflared hasta encontrar https://xxx.trycloudflare.com."""
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
            url = m.group(0).rstrip("/").strip("|, ")
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


def get_secret(name, quiet=False):
    """Lee un secreto del entorno o de los secretos de Kaggle (sin mostrarlo)."""
    v = os.environ.get(name, "").strip()
    if v:
        return v
    try:
        from kaggle_secrets import UserSecretsClient
        v = UserSecretsClient().get_secret(name) or ""
        if v.strip():
            return v.strip()
    except Exception as e:
        if not quiet:
            print(f"  (no se pudo leer el secreto de Kaggle: {e})")
    return ""


def get_cpk_key():
    return get_secret("CPK_INTELLIGENCE_API_KEY")


def kill_port(port):
    try:
        subprocess.run(["fuser", "-k", f"{port}/tcp"],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def start_node_proc(cmd, cwd, env, label):
    """Arranca un proceso con nvm/node cargado."""
    full = f'source "$NVM_DIR/nvm.sh" && nvm use 22 && {cmd}'
    proc = subprocess.Popen(
        ["bash", "-c", full],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    drain(proc, label)
    return proc


def write_env(path, env_vars):
    path.write_text("\n".join(f"{k}={v}" for k, v in env_vars.items()) + "\n")


# ----------------------------------------------------------
# 0. Limpieza de corridas anteriores
# ----------------------------------------------------------
print("[0/9] Liberando procesos/puertos de corridas anteriores...")
for _port in (8787, 8081):
    kill_port(_port)
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
    print("\n[1/9] Clonando sistema de persistencia...")
    subprocess.run(
        ["git", "clone", "https://github.com/enrrutador/openmuse-kaggle-persistence.git", str(REPO_DIR)],
        check=True,
    )
else:
    print("\n[1/9] Sistema de persistencia ya existe. Actualizando...")
    try:
        subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--ff-only"], check=True)
        print("  Repo actualizado ✓")
    except Exception as e:
        print(f"  [WARN] no se pudo actualizar ({e}), sigo con la copia local.")

sys.path.insert(0, str(REPO_DIR))

# ----------------------------------------------------------
# 2. Sistema de persistencia
# ----------------------------------------------------------
print("[2/9] Configurando persistencia...")

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


if (get_secret("RESET_DATA", quiet=True) or "").strip().lower() in ("1", "true", "yes"):
    print("  RESET_DATA=true: borrando datos locales, empiezo de cero...")
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_ZIP.exists():
        STATE_ZIP.unlink()
    print("  Datos locales borrados ✓")
else:
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
print("\n[3/9] Instalando OpenMuse (puede tardar)...")

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
    subprocess.run(
        "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash",
        shell=True, check=True,
    )


def run_with_node(cmd, cwd=None):
    full = f'source "$NVM_DIR/nvm.sh" && nvm install 22 --no-progress && nvm use 22 && {cmd}'
    return subprocess.run(full, shell=True, cwd=cwd, executable="/bin/bash")


run_with_node("node -v && npm -v")
run_with_node("npm install -g pnpm@11.19.0")
print("  Instalando dependencias de OpenMuse...")
run_with_node("pnpm install --frozen-lockfile || pnpm install", cwd=str(OPENMUSE_DIR))

# ----------------------------------------------------------
# 4. Clave CPK + cloudflared (sin arrancar túneles todavía)
# ----------------------------------------------------------
print("\n[4/9] Verificando clave CPK + cloudflared...")

cpk_key = get_cpk_key()
if not cpk_key:
    print("\n" + "=" * 60)
    print("  FALTA CPK_INTELLIGENCE_API_KEY — la API no puede arrancar sin ella.")
    print("  Cómo obtenerla (gratis, desde el iPhone):")
    print("  1. Safari → https://intelligence.copilotkit.ai → cuenta")
    print("  2. Creá un proyecto → API Keys → copiá la key cpk-...")
    print("  3. Kaggle: Add-ons → Secrets → CPK_INTELLIGENCE_API_KEY")
    print("  4. Adjuntá el secreto al notebook y re-ejecutá la celda.")
    print("=" * 60)
    raise SystemExit("Falta CPK_INTELLIGENCE_API_KEY")
print("  CPK_INTELLIGENCE_API_KEY presente ✓")

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

# ----------------------------------------------------------
# 5. Modelo + variables de entorno base
# ----------------------------------------------------------
print("\n[5/9] Configurando entorno base...")

provider_keys = {}
for _k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
    _v = get_secret(_k, quiet=True)
    if _v:
        provider_keys[_k] = _v
        print(f"  {_k} presente ✓")

nvidia_key = get_secret("NVIDIA_API_KEY", quiet=True)
if nvidia_key:
    print("  NVIDIA_API_KEY presente ✓")

backend = (get_secret("AGENT_BACKEND", quiet=True) or "").strip() or (
    "model" if (provider_keys or nvidia_key) else "sample"
)
model = (get_secret("MODEL", quiet=True) or "").strip()
using_nvidia = False

if backend == "model":
    if not model:
        if "GOOGLE_API_KEY" in provider_keys:
            model = "google/gemini-2.5-pro"
        elif "OPENAI_API_KEY" in provider_keys:
            model = "openai/gpt-5"
        elif "ANTHROPIC_API_KEY" in provider_keys:
            model = "anthropic/claude-sonnet-4.5"
        elif nvidia_key:
            model = "openai/moonshotai/kimi-k3"
    using_nvidia = (
        model.startswith("openai/")
        and "OPENAI_API_KEY" not in provider_keys
        and bool(nvidia_key)
    )
    if using_nvidia:
        provider_keys["OPENAI_API_KEY"] = nvidia_key
    if model and provider_keys:
        print(f"  Modelo real activado: {model} ✓ (backend=model)")
        if using_nvidia:
            print("  Gateway NVIDIA NIM ✓")
    else:
        print("  [WARN] backend=model pero falta MODEL o provider key")
else:
    print("  Agente de ejemplo (sample). Para modelo real agregá NVIDIA/GOOGLE/OPENAI/ANTHROPIC_API_KEY.")

# Env temporal: servicios locales primero. CORS permisivo para el primer arranque.
env_vars = {
    "DATA_DIR": str(DATA_DIR),
    "WORKSPACE_MODE": "sample",
    "AGENT_BACKEND": backend,
    "PORT": "8787",
    "HOST": "127.0.0.1",
    "PUBLIC_API_URL": "http://127.0.0.1:8787",
    "ALLOWED_ORIGINS": "*",
    "CPK_INTELLIGENCE_API_KEY": cpk_key,
    "TASK_WORKER_ENABLED": "true",
    "WEB_SEARCH_ENABLED": "true",
    "COMPUTER_ENABLED": "false",
    "EXPO_PUBLIC_API_URL": "http://127.0.0.1:8787",
}
if model:
    env_vars["MODEL"] = model
env_vars.update(provider_keys)
if using_nvidia:
    env_vars["OPENAI_BASE_URL"] = "https://integrate.api.nvidia.com/v1"

for k, v in env_vars.items():
    os.environ[k] = v

env_path = OPENMUSE_DIR / ".env"
write_env(env_path, env_vars)
print("  .env base escrito ✓ (servicios locales primero)")

# ----------------------------------------------------------
# 6. Arrancar API (puerto 8787) — ANTES de los túneles
# ----------------------------------------------------------
print("\n[6/9] Arrancando API de OpenMuse (puerto 8787)...")

api_env = os.environ.copy()
api_proc = start_node_proc("pnpm dev", OPENMUSE_DIR, api_env, "api")

if not wait_for_http("http://127.0.0.1:8787/api/health", timeout=150, label="API"):
    print("\n" + "=" * 60)
    print("  La API no levantó. Revisá los logs [api] arriba.")
    print("  Causa común: CPK_INTELLIGENCE_API_KEY inválida.")
    print("=" * 60)
    raise SystemExit("API no responde en /api/health")
print("  API en background ✓")

# ----------------------------------------------------------
# 7. Arrancar WEB (puerto 8081) — ANTES de los túneles
# ----------------------------------------------------------
print("\n[7/9] Arrancando interfaz web de OpenMuse (puerto 8081)...")

web_env = os.environ.copy()
web_proc = start_node_proc("pnpm dev:web", OPENMUSE_DIR, web_env, "web")

if not wait_for_http("http://127.0.0.1:8081/", timeout=240, label="Web"):
    print("\n" + "=" * 60)
    print("  La web no levantó. Revisá los logs [web] arriba.")
    print("=" * 60)
    raise SystemExit("Web no responde en puerto 8081")
print("  Interfaz web en background ✓")

# ----------------------------------------------------------
# 8. Ahora sí: túneles (origen ya está arriba → sin connection refused)
# ----------------------------------------------------------
print("\n[8/9] Creando túneles Cloudflare (origen ya vivo)...")

print("  Túnel API → http://127.0.0.1:8787 ...")
api_tunnel = subprocess.Popen(
    [str(cloudflared_path), "tunnel", "--url", "http://127.0.0.1:8787"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
api_url = wait_for_tunnel_url(api_tunnel, timeout=90, label="túnel API")
if api_url:
    print(f"  API pública: {api_url} ✓")
    drain(api_tunnel, "tunnel-api")
else:
    print("  [WARN] no se capturó URL de API")
    api_url = "http://127.0.0.1:8787"

print("  Túnel WEB → http://127.0.0.1:8081 ...")
web_tunnel = subprocess.Popen(
    [str(cloudflared_path), "tunnel", "--url", "http://127.0.0.1:8081"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
web_url = wait_for_tunnel_url(web_tunnel, timeout=90, label="túnel web")
if web_url:
    print(f"  Web pública: {web_url} ✓")
    drain(web_tunnel, "tunnel-web")
else:
    print("  [WARN] no se capturó URL web")
    web_url = None

# ----------------------------------------------------------
# 9. Reinicio rápido con URLs públicas (CORS + Expo)
# ----------------------------------------------------------
print("\n[9/9] Aplicando URLs públicas (CORS + EXPO_PUBLIC_API_URL)...")

allowed = "http://localhost:8081,http://127.0.0.1:8081"
if web_url:
    allowed += f",{web_url}"

env_vars["PUBLIC_API_URL"] = api_url
env_vars["EXPO_PUBLIC_API_URL"] = api_url
env_vars["ALLOWED_ORIGINS"] = allowed

for k, v in env_vars.items():
    os.environ[k] = v
write_env(env_path, env_vars)
print(f"  .env final ✓ (PUBLIC_API_URL={api_url})")
print(f"  ALLOWED_ORIGINS={allowed}")

# Reiniciar API y WEB con el env correcto (los túneles siguen apuntando a los puertos)
print("  Reiniciando API y WEB con URLs públicas...")
try:
    api_proc.terminate()
except Exception:
    pass
try:
    web_proc.terminate()
except Exception:
    pass
time.sleep(2)
kill_port(8787)
kill_port(8081)
time.sleep(1)

api_env = os.environ.copy()
api_proc = start_node_proc("pnpm dev", OPENMUSE_DIR, api_env, "api")
if not wait_for_http("http://127.0.0.1:8787/api/health", timeout=120, label="API (reinicio)"):
    print("  [WARN] API no respondió tras reinicio; los túneles pueden seguir con la instancia anterior")
else:
    print("  API reiniciada ✓")

web_env = os.environ.copy()
web_proc = start_node_proc("pnpm dev:web", OPENMUSE_DIR, web_env, "web")
if not wait_for_http("http://127.0.0.1:8081/", timeout=180, label="Web (reinicio)"):
    print("  [WARN] Web no respondió tras reinicio")
else:
    print("  Web reiniciada ✓")

# ----------------------------------------------------------
# Resultado final + keep-alive
# ----------------------------------------------------------
print("\n" + "=" * 60)
if web_url:
    print("  LISTO — en el iPhone abrí ESTA (la de la WEB):")
    print(f"  {web_url}")
    print("")
    print("  NO abras la de la API en Safari (es solo backend):")
    print(f"  API: {api_url}")
else:
    print("  Servidores arrancados, pero no se pudo capturar la URL web.")
    print(f"  API pública (por si sirve): {api_url}")
    print("  Revisá los logs [tunnel-web] arriba.")
print("  Auto-save cada 5 minutos activo.")
print("  Para forzar guardado: save_state('manual')")
print(f"  VERSION: {VERSION}")
print("=" * 60)

print("\n[keep-alive] Celda viva. Stop para terminar.")
try:
    while True:
        time.sleep(60)
        for name, p in [
            ("api", api_proc),
            ("web", web_proc),
            ("tunnel-api", api_tunnel),
            ("tunnel-web", web_tunnel),
        ]:
            if p.poll() is not None:
                print(f"  [WARN] {name} terminó con exit={p.poll()}")
except KeyboardInterrupt:
    print("  Keep-alive interrumpido.")
