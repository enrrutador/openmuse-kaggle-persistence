# OpenMuse Kaggle Persistence

Sistema de **persistencia real** para OpenMuse en Kaggle + acceso público con Cloudflare Tunnel.

## Objetivo

- Se cae la sesión de Kaggle → reiniciás → continúa donde lo dejaste
- Guardado automático cada 5 minutos
- La URL pública **abre directamente la interfaz de OpenMuse**
- **Todo en una sola celda**
- Arranque **directo**: primero servicios, después túneles (sin `connection refused`)

## Versión actual

`2026-10-05.13-thread-heal` — corrige 404 THREAD_NOT_FOUND + menú colgado

Además del orden de arranque, cada corrida aplica `scripts/heal_threads_patch.py`
sobre `/kaggle/working/openmuse`:

1. `/api/main-thread`: si Intelligence devuelve `THREAD_NOT_FOUND`/404 para el
   hilo guardado, borra el registro local y crea un UUID fresco (`existing:false`).
2. `/api/copilotkit/*`: traduce `THREAD_NOT_FOUND` a 409 con mensaje accionable
   en vez de `404 404 page not found`.
3. `ThreadsProvider`: faltaba `setLoading(false)` en el catch → spinner eterno
   y botón menú (3 rayitas) inutilizable. Parcheado.

Notas honestas:

- La UI de OpenMuse alpha es solo inglés, no tiene selector de idioma.
  Pedile al agente `Responde siempre en español` y usá Traducir de Safari para los botones.
- El menú de 3 rayitas es la hoja de conversaciones (depende de Intelligence).
  Si muestra error, tocá `Retry main chat` / `New side chat`.
- Si el chat sigue en 404 tras el parche: creá un proyecto nuevo en
  `intelligence.copilotkit.ai` (key server-only `cpk-...`, no `pk-...`),
  poné `RESET_DATA=true` como secreto, re-ejecutá, sacalo y re-ejecutá normal,
  y abrí la URL WEB en ventana privada.

Orden de arranque (fix del 404):

1. Limpieza robusta (pkill cloudflared/pnpm/expo + fuser 8787/8081)
2. Persistencia (restore + auto-save)
3. Instalar OpenMuse
4. Verificar `CPK_INTELLIGENCE_API_KEY`
5. Arrancar **solo API** (8787) en local + verificar `POST /api/session`
6. Crear **túnel API** → obtener `api_url` real + verificar salud pública
7. Arrancar **WEB una sola vez** ya con `EXPO_PUBLIC_API_URL=api_url` y `--clear`
8. Crear **túnel WEB** → obtener `web_url`
9. Reiniciar **solo API** para CORS final (la WEB queda intacta, su bundle ya es correcto)
10. Verificación end-to-end + keep-alive

Por qué existía el 404: la versión anterior arrancaba WEB con `localhost`,
Metro cacheaba ese bundle, y el reinicio con `terminate()` no mataba los hijos.
El iPhone pedía `http://127.0.0.1:8787/api/copilotkit` y fallaba.

## Requisito: CPK_INTELLIGENCE_API_KEY

OpenMuse la exige siempre (hasta en modo sample). Sin ella la celda aborta en el paso [4/9] con instrucciones. Es gratis y se saca desde el iPhone:

1. En Safari abrí <https://intelligence.copilotkit.ai> y creá tu cuenta
2. Creá un proyecto y andá a la página API Keys del proyecto
3. Copiá la key que empieza con `cpk-...`
4. En Kaggle: Add-ons → Secrets → Add secret, nombre `CPK_INTELLIGENCE_API_KEY`, pegá la key y adjuntá el secreto al notebook
5. Re-ejecutá la celda

## Modelo real (opcional)

Sin esto queda el agente de ejemplo (respuestas guionadas). Para un modelo de verdad, con secretos de Kaggle:

- **NVIDIA (gratis)**: secreto `NVIDIA_API_KEY` (usa `openai/moonshotai/kimi-k3` por defecto; para GLM agregá `MODEL` = `openai/z-ai/glm-5-3-flash`)
- **Google**: secreto `GOOGLE_API_KEY` (usa `google/gemini-2.5-pro` por defecto)
- **OpenAI**: secreto `OPENAI_API_KEY`
- **Anthropic**: secreto `ANTHROPIC_API_KEY`
- Otro modelo: secreto extra `MODEL`, ej. `google/gemini-2.5-flash`

Con alguna provider key la celda activa `backend=model` sola.

## Cómo usarlo

1. Creá un notebook nuevo en Kaggle
2. Activá **Internet** en Settings
3. Copiá y pegá esta celda bootstrap (siempre baja la última versión):

```python
import urllib.request
urllib.request.urlretrieve(
    "https://raw.githubusercontent.com/enrrutador/openmuse-kaggle-persistence/main/notebook/one_cell.py",
    "/tmp/one_cell_latest.py")
exec(compile(open("/tmp/one_cell_latest.py").read(), "one_cell_latest.py", "exec"))
```

4. Ejecutá la celda
5. Verificá que imprima `VERSION: 2026-10-05.13-thread-heal`
6. Te va a imprimir DOS URLs (tipo `https://xxxx.trycloudflare.com`):
   - `Web pública` → **esta es la que abrís en Safari del iPhone**
   - `API` → no la abras como app, es solo backend
7. En la app tocá `Open workspace` sin key en modo sample.
   Si el chat da 404, mirá el bloque `Diagnóstico chat` que imprime la celda:
   `POST público /api/session` tiene que decir `OK`. Si dice `FALLO`,
   no abras la app: el túnel API se cayó o la CPK key es inválida.

## Importante

- La URL de Cloudflare cambia cada vez que reiniciás el notebook
- Para que el estado sobreviva a reinicios largos, hacé **Save Version** de vez en cuando
- Si algo queda roto por un hilo viejo de CopilotKit: secreto `RESET_DATA=true` y re-ejecutá

## Repo

https://github.com/enrrutador/openmuse-kaggle-persistence
