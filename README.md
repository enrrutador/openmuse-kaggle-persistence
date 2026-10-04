# OpenMuse Kaggle Persistence

Sistema de **persistencia real** para OpenMuse en Kaggle + acceso público con Cloudflare Tunnel.

## Objetivo

- Se cae la sesión de Kaggle → reiniciás → continúa donde lo dejaste
- Guardado automático cada 5 minutos
- La URL pública **abre directamente la interfaz de OpenMuse**
- **Todo en una sola celda**

## Cómo usarlo

1. Creá un notebook nuevo en Kaggle
2. Activá **Internet** en Settings
3. Copiá y pegá el contenido de `notebook/one_cell.py`
4. Ejecutá la celda
5. Te va a imprimir una URL (tipo `https://xxxx.trycloudflare.com`)
6. Abrí esa URL en Safari del iPhone → se abre OpenMuse

## Importante

- La URL de Cloudflare cambia cada vez que reiniciás el notebook
- Para que el estado sobreviva a reinicios largos, hacé **Save Version** de vez en cuando
- Estamos usando modo `sample` de OpenMuse (no necesita claves de OpenAI ni CopilotKit)

## Repo

https://github.com/enrrutador/openmuse-kaggle-persistence
