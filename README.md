# OpenMuse Kaggle Persistence

Sistema de **persistencia real** para OpenMuse en Kaggle + acceso público con Cloudflare Tunnel.

## Objetivo

- Se cae la sesión de Kaggle → reiniciás → continúa donde lo dejaste
- Guardado automático cada 5 minutos
- La URL pública **abre directamente la interfaz de OpenMuse**
- **Todo en una sola celda**
- Arranque **directo**: primero servicios, después túneles (sin `connection refused`)

## Versión actual

`2026-10-04.10-direct`

Orden de arranque:

1. Limpieza de puertos
2. Persistencia (restore + auto-save)
3. Instalar OpenMuse
4. Verificar `CPK_INTELLIGENCE_API_KEY`
5. Arrancar **API** (8787) y **Web** (8081) en local
6. Cuando ambos responden → crear túneles Cloudflare
7. Reinicio rápido con URLs públicas (CORS + Expo)
8. Keep-alive

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
5. Verificá que imprima `VERSION: 2026-10-04.10-direct`
6. Te va a imprimir una URL (tipo `https://xxxx.trycloudflare.com`)
7. Abrí esa URL en Safari del iPhone → se abre OpenMuse

## Importante

- La URL de Cloudflare cambia cada vez que reiniciás el notebook
- Para que el estado sobreviva a reinicios largos, hacé **Save Version** de vez en cuando
- Si algo queda roto por un hilo viejo de CopilotKit: secreto `RESET_DATA=true` y re-ejecutá

## Repo

https://github.com/enrrutador/openmuse-kaggle-persistence
