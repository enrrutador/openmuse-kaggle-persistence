# OpenMuse Kaggle Persistence

Sistema de **persistencia real** para OpenMuse en Kaggle + acceso público con Cloudflare Tunnel.

## Objetivo

- Se cae la sesión de Kaggle → reiniciás → continúa donde lo dejaste
- Guardado automático cada 5 minutos
- La URL pública **abre directamente la interfaz de OpenMuse**
- **Todo en una sola celda**

## Requisito: CPK_INTELLIGENCE_API_KEY

OpenMuse la exige siempre (hasta en modo sample). Sin ella la celda aborta en el paso [4/8] con instrucciones.

1. Una vez, en tu laptop: `npx copilotkit@latest login` y `npx copilotkit@latest project select`
2. Copiá la server-only key generada
3. En Kaggle: Add-ons → Secrets → Add secret, nombre `CPK_INTELLIGENCE_API_KEY`, pegá la key y adjuntá el secreto al notebook
4. Re-ejecutá la celda

## Cómo usarlo

1. Creá un notebook nuevo en Kaggle
2. Activá **Internet** en Settings
3. Copiá y pegá esta celda bootstrap (siempre baja la última versión, no queda código viejo pegado):

```python
import urllib.request
urllib.request.urlretrieve(
    "https://raw.githubusercontent.com/enrrutador/openmuse-kaggle-persistence/main/notebook/one_cell.py",
    "/tmp/one_cell_latest.py")
exec(compile(open("/tmp/one_cell_latest.py").read(), "one_cell_latest.py", "exec"))
```

4. Ejecutá la celda
5. Verificá que imprima `VERSION: 2026-10-04.4` (si no, tu celda tiene código viejo)
6. Te va a imprimir una URL (tipo `https://xxxx.trycloudflare.com`)
7. Abrí esa URL en Safari del iPhone → se abre OpenMuse

## Importante

- La URL de Cloudflare cambia cada vez que reiniciás el notebook
- Para que el estado sobreviva a reinicios largos, hacé **Save Version** de vez en cuando
- Estamos usando modo `sample` de OpenMuse (no necesita claves de OpenAI ni CopilotKit)

## Repo

https://github.com/enrrutador/openmuse-kaggle-persistence
