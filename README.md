# OpenMuse Kaggle Persistence

Sistema de **persistencia real** para OpenMuse en Kaggle.

## Objetivo

- Se cae la sesión de Kaggle o se apaga el notebook
- Reiniciás el notebook
- OpenMuse **continúa exactamente donde lo dejaste**

El estado (conversaciones, tareas, archivos, base de datos, etc.) se guarda automáticamente cada 5 minutos.

> **Nota:** No usamos ngrok. La exposición pública se dejará para una solución alternativa más adelante.

## Cómo funciona

1. Al iniciar el notebook se restaura el estado anterior (si existe).
2. Se clona e instala OpenMuse.
3. OpenMuse corre usando el directorio de datos persistente.
4. Cada 5 minutos se guarda un snapshot completo del estado.
5. Al hacer **Save Version** en Kaggle, el estado queda persistido para la próxima sesión.

## Estructura del repo

```
openmuse-kaggle-persistence/
├── README.md
├── notebook/
│   └── openmuse_kaggle.ipynb
├── persistence/
│   ├── state.py
│   └── auto_save.py
├── scripts/
│   └── setup_openmuse.sh
└── .gitignore
```

## Estado actual

- [x] Repositorio creado
- [x] Sistema de persistencia (guardar / restaurar)
- [x] Auto-save cada 5 minutos
- [x] Scripts de instalación de OpenMuse
- [ ] Notebook completo listo para copiar y pegar
- [ ] Integración final del servidor
- [ ] Solución de acceso público (sin ngrok)

## Uso (en desarrollo)

1. Creá un notebook nuevo en Kaggle
2. Activá **Internet** y **GPU** (recomendado)
3. Copiá el contenido del notebook de este repo
4. Ejecutá las celdas en orden

---

Hecho para usarse **sin PC**, solo desde el iPhone.
