# OpenMuse Kaggle Persistence

Sistema de **persistencia real** para OpenMuse en Kaggle.

## Objetivo

- Se cae la sesión de Kaggle o se apaga el notebook
- Reiniciás el notebook
- OpenMuse **continúa exactamente donde lo dejaste**

El estado (conversaciones, tareas, archivos, base de datos, etc.) se guarda automáticamente cada 5 minutos.

> **Nota:** No usamos ngrok. La forma de acceder desde el iPhone se definirá más adelante.

## Cómo funciona

1. Al iniciar el notebook se restaura el estado anterior (si existe).
2. Se clona e instala OpenMuse.
3. OpenMuse corre usando el directorio de datos persistente (`/kaggle/working/openmuse-data`).
4. Cada 5 minutos se guarda un snapshot completo del estado en `openmuse_state.zip`.
5. Al hacer **Save Version** en Kaggle, el estado queda disponible para la próxima sesión.

## Estructura del repo

```
openmuse-kaggle-persistence/
├── README.md
├── notebook/
│   └── openmuse_kaggle.ipynb      # Notebook principal listo para usar
├── persistence/
│   ├── state.py                  # Guardar / restaurar estado
│   └── auto_save.py              # Loop de guardado automático
├── scripts/
│   └── setup_openmuse.sh         # Instalación de OpenMuse
└── .gitignore
```

## Cómo usarlo (desde el iPhone)

1. Entrá a [Kaggle](https://www.kaggle.com) y creá un notebook nuevo.
2. En **Settings** del notebook:
   - Activá **Internet**
   - (Opcional) Activá GPU si querés más potencia
3. Copiá el contenido de `notebook/openmuse_kaggle.ipynb` o ejecutá las celdas una por una.
4. Ejecutá las celdas **en orden**.
5. Cuando quieras asegurar la persistencia a largo plazo, hacé **Save Version**.

## Estado del proyecto

- [x] Sistema de persistencia (guardar / restaurar)
- [x] Auto-save cada 5 minutos
- [x] Scripts de instalación de OpenMuse
- [x] Notebook funcional
- [x] Manejo de errores básico
- [ ] Acceso público desde el iPhone (sin ngrok)
- [ ] Optimizaciones de recursos para Kaggle

## Notas importantes

- El estado vive en `/kaggle/working`. Para que sobreviva a un reinicio completo del kernel, hacé **Save Version**.
- OpenMuse en modo `sample` no necesita claves de OpenAI ni CopilotKit Intelligence.
- La primera instalación puede tardar varios minutos.

---

Hecho para usarse **sin PC**, solo desde el iPhone.
