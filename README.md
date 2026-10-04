# OpenMuse Kaggle Persistence

Sistema de **persistencia real** para OpenMuse en Kaggle + acceso público con Cloudflare Tunnel.

## Objetivo

- Se cae la sesión de Kaggle → reiniciás → continúa donde lo dejaste
- Guardado automático cada 5 minutos
- URL pública con Cloudflare Tunnel (sin ngrok)
- **Todo en una sola celda**

## Cómo usarlo

1. Creá un notebook nuevo en Kaggle
2. Activá **Internet** en Settings
3. Copiá y pegá **solo la celda** que está en `notebook/one_cell.py`
4. Ejecutá
5. Te va a imprimir una URL pública (tipo `https://xxxx.trycloudflare.com`)
6. Esa URL la podés usar en OpenCode u otra herramienta

## Importante

- La URL de Cloudflare cambia cada vez que reiniciás el notebook
- Para que el estado sobreviva a reinicios largos, hacé **Save Version** de vez en cuando
- Estamos usando modo `sample` de OpenMuse (no necesita claves)

## Repo

https://github.com/enrrutador/openmuse-kaggle-persistence
