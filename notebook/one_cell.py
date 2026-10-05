# ============================================================
# OPENMUSE EN KAGGLE - TODO EN UNA SOLA CELDA
# Persistencia real + Cloudflare Tunnel
# VERSION FIXED: API -> tunel API -> WEB (una sola vez con URL real) -> tunel WEB
# (corrige 404 en chat por bundle Metro stale + kill incompleto)
# v13: auto-heal THREAD_NOT_FOUND (regenera hilo) + fix spinner menú colgado
# ============================================================

import os
import re
import sys
import time
import json
import socket
import subprocess
import threading
import zipfile
import shutil
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

VERSION = "2026-10-05.18-model-selector"

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


def http_json(url, data=None, headers=None, timeout=15):
    """GET (data=None) o POST JSON. Retorna (status, payload)."""
    hdrs = dict(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode(errors="replace")
            try:
                return r.status, json.loads(raw) if raw else {}
            except Exception:
                return r.status, {"_raw": raw[:500]}
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode(errors="replace")
        except Exception:
            raw = ""
        return e.code, {"_raw": raw[:1000]}
    except Exception as e:
        return -1, {"_error": str(e)[:500]}


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


def port_open(port, host="127.0.0.1"):
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def kill_port(port):
    try:
        subprocess.run(["fuser", "-k", f"{port}/tcp"],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    # Fallback por si fuser no existe: intentar lsof
    try:
        r = subprocess.run(["lsof", "-ti", f":{port}"],
                           capture_output=True, text=True, timeout=10)
        for pid in (r.stdout or "").split():
            try:
                subprocess.run(["kill", "-9", pid.strip()],
                               capture_output=True, timeout=5)
            except Exception:
                pass
    except Exception:
        pass


def kill_patterns():
    for pat in ("cloudflared", "pnpm dev", "expo start", "tsx watch",
                "tsx apps/server", "metro", "openmuse"):
        try:
            subprocess.run(["pkill", "-9", "-f", pat],
                           capture_output=True, timeout=10)
        except Exception:
            pass


def stop_proc(proc, label="proc", timeout=8):
    """Para un Popen de forma robusta (terminate -> kill + pkill fallback)."""
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
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
# 0. Limpieza de corridas anteriores (robusta)
# ----------------------------------------------------------
print("[0/10] Liberando procesos/puertos de corridas anteriores...")
kill_patterns()
for _port in (8787, 8081):
    kill_port(_port)
time.sleep(3)
# Segundo intento por si algo reapareció
kill_patterns()
for _port in (8787, 8081):
    if port_open(_port):
        kill_port(_port)
time.sleep(2)
if port_open(8787) or port_open(8081):
    print("  [WARN] algún puerto sigue ocupado, sigo igual (puede fallar el bind).")
else:
    print("  Puertos liberados ✓")


# ----------------------------------------------------------
# 1. Clonar este repo de persistencia
# ----------------------------------------------------------
REPO_DIR = Path("/kaggle/working/openmuse-kaggle-persistence")
if not REPO_DIR.exists():
    print("\n[1/10] Clonando sistema de persistencia...")
    subprocess.run(
        ["git", "clone", "https://github.com/enrrutador/openmuse-kaggle-persistence.git", str(REPO_DIR)],
        check=True,
    )
else:
    print("\n[1/10] Sistema de persistencia ya existe. Actualizando...")
    try:
        subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--ff-only"], check=True)
        print("  Repo actualizado ✓")
    except Exception as e:
        print(f"  [WARN] no se pudo actualizar ({e}), sigo con la copia local.")

sys.path.insert(0, str(REPO_DIR))

# ----------------------------------------------------------
# 2. Sistema de persistencia
# ----------------------------------------------------------
print("[2/10] Configurando persistencia...")

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
print("\n[3/10] Instalando OpenMuse (puede tardar)...")

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

# Parches thread-heal: THREAD_NOT_FOUND auto-regenera hilo + fix spinner menú.
# (parchea /kaggle/working/openmuse en cada corrida; tsx watch lo recarga solo)
print("  Aplicando parches thread-heal...")
try:
    sys.path.insert(0, str(REPO_DIR / "scripts"))
    from heal_threads_patch import apply as apply_thread_heal
    apply_thread_heal(OPENMUSE_DIR)
except Exception as e:
    print(f"  [WARN] no se pudo aplicar parche thread-heal: {e}")

# ----------------------------------------------------------
# 4. Clave CPK + cloudflared
# ----------------------------------------------------------
print("\n[4/10] Verificando clave CPK + cloudflared...")

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
# 5. Modelo + variables de entorno base (local primero)
# ----------------------------------------------------------
print("\n[5/10] Configurando entorno base...")

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
if not model:
    # Override elegido desde el selector de la app (Apps & settings).
    # El secreto MODEL lo pisa si lo ponés. Vive en DATA_DIR → persiste.
    try:
        _ovf = DATA_DIR / "model-override.json"
        if _ovf.exists():
            _om = (json.loads(_ovf.read_text()) or {}).get("model", "")
            if isinstance(_om, str) and _om.strip():
                model = _om.strip()
                print(f"  Modelo del selector de la app: {model} ✓ (secreto MODEL lo pisa)")
    except Exception as _e:
        print(f"  [WARN] no pude leer model-override.json: {_e}")
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
            model = "openai/z-ai/glm-5.3-flash"
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

# Lista de modelos NVIDIA de TU key para que elijas con el secreto MODEL.
# (build.nvidia.com marca cuáles tienen endpoint gratis; acá salen los que tu key ve.)
nvidia_models = []
if using_nvidia:
    _lst, _lp = http_json(
        "https://integrate.api.nvidia.com/v1/models",
        headers={"Authorization": f"Bearer {provider_keys.get('OPENAI_API_KEY', '')}"},
        timeout=20,
    )
    if _lst == 200 and isinstance(_lp, dict) and isinstance(_lp.get("data"), list):
        nvidia_models = sorted({m.get("id") for m in _lp["data"] if isinstance(m, dict) and m.get("id")})
    if nvidia_models:
        print(f"  Modelos NVIDIA para tu key ({len(nvidia_models)}):")
        _cur = model.split("/", 1)[1] if model.startswith("openai/") else model
        for _i, _id in enumerate(nvidia_models, 1):
            _mark = "  <-- actual" if _id == _cur else ""
            print(f"    {_i:3d}. MODEL=openai/{_id}{_mark}")
        print("  Para cambiar: secreto MODEL=openai/<id> y re-ejecutá.")
        # Los free de la foto, con su ID exacto de API (si tu key los ve):
        _free = {
            "z-ai/glm-5.3-flash": "GLM-5.3-Flash",
            "moonshotai/kimi-k3": "Kimi K3",
            "nvidia/nemotron-3.5-lightning-30b-a3b": "Nemotron 3.5 Lightning 30B A3B",
            "meta/muse-glimmer-30b": "Muse Glimmer 30B",
            "nvidia/llama-3.1-nemotron-70b-instruct": "Llama 3.1 Nemotron 70B (bueno con tools)",
        }
        _found = [(k, v) for k, v in _free.items() if k in nvidia_models]
        if _found:
            print("  Free de tu foto visibles para tu key:")
            for _id, _name in _found:
                _mark = "  <-- actual" if _id == _cur else ""
                print(f"    - {_name}: MODEL=openai/{_id}{_mark}")
            print("  Nota: Kimi K3 pasa el preflight pero el agente lo rechaza (404).")
            print("  Si Kimi falla en el chat, usá GLM-5.3-Flash o Llama 3.1 8B.")
        if _cur not in nvidia_models:
            print(f"  [WARN] tu MODEL actual ({model}) no está en la lista de tu key.")
    else:
        print(f"  [WARN] no pude listar modelos NVIDIA ({_lst}). Revisá NVIDIA_API_KEY.")
else:
    print("  Agente de ejemplo (sample). Para modelo real agregá NVIDIA/GOOGLE/OPENAI/ANTHROPIC_API_KEY.")

# Preflight del modelo: detecta ANTES de arrancar si el gateway responde 404/401.
# El 404 del chat en convertTanStackStream viene de acá, no de los túneles.
model_preflight = "skip (backend=sample o provider nativo)"
if backend == "model" and model.startswith("openai/"):
    _base = "https://integrate.api.nvidia.com/v1" if using_nvidia else "https://api.openai.com/v1"
    _key = provider_keys.get("OPENAI_API_KEY", "")
    _mid = model.split("/", 1)[1]
    print(f"  Preflight modelo: POST {_base}/chat/completions model={_mid} ...")
    _st, _pay = http_json(
        f"{_base}/chat/completions",
        data={"model": _mid, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
        headers={"Authorization": f"Bearer {_key}"},
        timeout=30,
    )
    if _st == 200:
        model_preflight = "OK"
        print("  Modelo responde ✓ (preflight OK)")
    else:
        model_preflight = f"FALLO {_st}"
        print(f"  [ERROR] preflight modelo -> {_st} {str(_pay)[:500]}")
        if _st == 404:
            print("  El gateway no tiene ese modelo para tu key. Elegí uno de la lista de arriba")
            print("  con secreto MODEL=openai/<id> y re-ejecutá.")
        elif _st == 401:
            print("  Key inválida o vencida. Regenerala y re-ejecutá.")
        print("  El chat dará 404 hasta que el preflight diga OK.")

# Env base: servicios locales primero. CORS permisivo para el primer arranque.
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
# 6. Arrancar SOLO API (puerto 8787) — ANTES de cualquier túnel
# ----------------------------------------------------------
print("\n[6/10] Arrancando API de OpenMuse (puerto 8787)...")

api_env = os.environ.copy()
api_proc = start_node_proc("pnpm dev", OPENMUSE_DIR, api_env, "api")

if not wait_for_http("http://127.0.0.1:8787/api/health", timeout=150, label="API"):
    print("\n" + "=" * 60)
    print("  La API no levantó. Revisá los logs [api] arriba.")
    print("  Causa común: CPK_INTELLIGENCE_API_KEY inválida.")
    print("=" * 60)
    raise SystemExit("API no responde en /api/health")

# Verificación local de sesión (esto es lo que el chat usa; si da 404 acá, el chat dará 404)
st, payload = http_json("http://127.0.0.1:8787/api/session", data={})
print(f"  POST /api/session local -> {st} {str(payload)[:200]}")
if st == 404:
    print("  [WARN] /api/session local da 404: versión de OpenMuse incompatible. Revisá git pull de /kaggle/working/openmuse.")
print("  API en background ✓")

# ----------------------------------------------------------
# 7. Túnel API primero → obtener api_url pública real
# ----------------------------------------------------------
print("\n[7/10] Creando túnel API (origen ya vivo)...")

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
    print("  [ERROR] no se capturó URL de API, no puedo seguir sin EXPO_PUBLIC_API_URL real.")
    raise SystemExit("Sin api_url no se puede compilar la web (causaría 404 en chat)")

# Verificar que la API responde A TRAVÉS del túnel (Cloudflare a veces tarda)
print("  Verificando API pública a través del túnel...")
if not wait_for_http(f"{api_url}/api/health", timeout=120, label="API pública"):
    print("  [WARN] la API pública no responde todavía, sigo igual (puede ser delay de Cloudflare).")
else:
    st, payload = http_json(f"{api_url}/api/session", data={})
    print(f"  POST {api_url}/api/session -> {st} {str(payload)[:200]}")
    if st == 404:
        print("  [ERROR] la API pública da 404 en /api/session. El túnel apunta mal.")
    elif st == -1:
        print(f"  [WARN] no se pudo validar sesión pública: {payload}")

# ----------------------------------------------------------
# 8. Arrancar WEB UNA SOLA VEZ, ya con la api_url real (con --clear)
# FIX 404: antes se arrancaba con localhost y se cacheaba en Metro.
# ----------------------------------------------------------
print("\n[8/10] Arrancando interfaz web UNA vez con URL real (puerto 8081)...")

env_vars["PUBLIC_API_URL"] = api_url
env_vars["EXPO_PUBLIC_API_URL"] = api_url
# CORS temporal: localhost + api pública. El web_url aún no existe, se agrega en [9/10].
env_vars["ALLOWED_ORIGINS"] = "http://localhost:8081,http://127.0.0.1:8081"
for k, v in env_vars.items():
    os.environ[k] = v
write_env(env_path, env_vars)
print(f"  .env web ✓ (EXPO_PUBLIC_API_URL={api_url})")

web_env = os.environ.copy()
# --clear evita bundle stale de corridas anteriores con localhost
web_proc = start_node_proc("pnpm --dir apps/mobile web -- --clear", OPENMUSE_DIR, web_env, "web")

if not wait_for_http("http://127.0.0.1:8081/", timeout=240, label="Web"):
    print("\n" + "=" * 60)
    print("  La web no levantó. Revisá los logs [web] arriba.")
    print("=" * 60)
    raise SystemExit("Web no responde en puerto 8081")
print("  Interfaz web en background ✓ (compilada contra API pública real)")

# ----------------------------------------------------------
# 9. Túnel WEB + reinicio SOLO de API para CORS final
# La WEB NO se reinicia (su bundle ya es correcto).
# ----------------------------------------------------------
print("\n[9/10] Creando túnel WEB + ajuste CORS final...")

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

# Reiniciar SOLO API con el env correcto (el túnel sigue apuntando al puerto 8787)
print("  Reiniciando SOLO API con CORS final (la WEB queda intacta)...")
stop_proc(api_proc, "api")
kill_port(8787)
time.sleep(2)

api_env = os.environ.copy()
api_proc = start_node_proc("pnpm dev", OPENMUSE_DIR, api_env, "api")
if not wait_for_http("http://127.0.0.1:8787/api/health", timeout=120, label="API (reinicio)"):
    print("  [WARN] API no respondió tras reinicio; revisá logs [api]")
else:
    print("  API reiniciada ✓")

# ----------------------------------------------------------
# 10. Verificación final end-to-end (esto evita el 404 en chat)
# ----------------------------------------------------------
print("\n[10/10] Verificación final...")

ok_local = wait_for_http("http://127.0.0.1:8787/api/health", timeout=30, label="API local final")
ok_web_local = wait_for_http("http://127.0.0.1:8081/", timeout=30, label="Web local final")

ok_api_pub = False
ok_sess_pub = False
ok_thread = False
sess_token = ""
if api_url:
    ok_api_pub = wait_for_http(f"{api_url}/api/health", timeout=60, label="API pública final")
    st, payload = http_json(f"{api_url}/api/session", data={})
    print(f"  POST público /api/session -> {st} {str(payload)[:300]}")
    ok_sess_pub = (st == 200)
    if isinstance(payload, dict) and payload.get("token"):
        sess_token = payload["token"]
    if st == 404:
        print("  [ERROR] /api/session pública = 404. Causas: túnel API caído o OpenMuse desactualizado en /kaggle/working/openmuse.")
        print("  Fix: borrá /kaggle/working/openmuse y re-ejecutá (hace git clone fresco).")
    elif st == 429:
        print("  (429 demasiados intentos, esperá 1 min y reintentá en la app.)")
    elif st == -1:
        print(f"  [WARN] sin conexión pública a sesión: {payload}")
    if ok_sess_pub and sess_token:
        tst, tpayload = http_json(
            f"{api_url}/api/main-thread",
            headers={"Authorization": f"Bearer {sess_token}"},
        )
        print(f"  GET público /api/main-thread -> {tst} {str(tpayload)[:300]}")
        ok_thread = (tst == 200)
        if tst == 502:
            print("  [ERROR] Intelligence no pudo crear el hilo. Revisá CPK_INTELLIGENCE_API_KEY (tiene que ser server-only cpk-...).")
        elif tst == 409:
            print("  (409 hilo regenerado, reintentá en la app con nueva conversación.)")

ok_web_pub = False
if web_url:
    ok_web_pub = wait_for_http(web_url + "/", timeout=60, label="Web pública final")

print("")
print("  Diagnóstico chat:")
print(f"    EXPO_PUBLIC_API_URL compilado = {api_url}")
print(f"    API local /api/health: {'OK' if ok_local else 'FALLO'}")
print(f"    API pública /api/health: {'OK' if ok_api_pub else 'FALLO'}")
print(f"    POST público /api/session (lo que usa el chat): {'OK' if ok_sess_pub else 'FALLO'}")
print(f"    Modelo preflight [5/10]: {model_preflight}")
print(f"    GET público /api/main-thread (hilo Intelligence): {'OK' if ok_thread else 'FALLO'}")
print(f"    Web pública: {'OK' if ok_web_pub else 'FALLO'}")
if not ok_sess_pub:
    print("    → Si esto falla, el chat dará 404. No abras la app hasta que diga OK.")
    print("    → Revisá: 1) túnel API vivo ([tunnel-api] sin errores), 2) ALLOWED_ORIGINS incluye tu web_url, 3) CPK key válida.")

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
    print("")
    print("  Cómo usar:")
    print("  - En modo sample: tocá 'Open workspace' sin key (datos de ejemplo: Alex).")
    print("  - Para modelo real: agregá NVIDIA_API_KEY / GOOGLE_API_KEY / OPENAI_API_KEY")
    print("    como secreto de Kaggle y re-ejecutá (backend=model solo).")
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
