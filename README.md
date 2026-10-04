# OpenMuse Kaggle Persistence

Sistema de **persistencia real** para OpenMuse en Kaggle.

## Objetivo

- Se cae la sesión de Kaggle o se apaga el notebook
- Reiniciás el notebook
- OpenMuse **continúa exactamente donde lo dejaste**

El estado (conversaciones, tareas, archivos, base de datos, etc.) se guarda automáticamente cada 5 minutos.

## Cómo funciona

1. Al iniciar el notebook se restaura el estado anterior (si existe).
2. OpenMuse corre normalmente.
3. Cada 5 minutos se guarda un snapshot completo del estado en `/kaggle/working/openmuse_state.zip`.
4. Al hacer **Save Version** en Kaggle, el estado queda persistido.
5. La próxima vez que abras el notebook, se restaura automáticamente.

## Estructura

```
openmuse-kaggle-persistence/
├── README.md
├── notebook/
│   └── openmuse_kaggle.ipynb   # Notebook principal
├── persistence/
│   ├── state.py               # Lógica de guardado/restauración
│   └── auto_save.py           # Loop de guardado automático
└── scripts/
    └── setup.sh               # Instalación de dependencias
```

## Estado actual

- [x] Repositorio creado
- [ ] Sistema de persistencia (en progreso)
- [ ] Notebook completo de Kaggle
- [ ] Integración con OpenMuse
- [ ] ngrok + URL pública
- [ ] Documentación de uso desde iPhone

## Uso rápido (próximamente)

1. Fork o clona este repo
2. Crea un notebook en Kaggle
3. Copia el contenido de `notebook/openmuse_kaggle.ipynb`
4. Ejecutá las celdas

---

Hecho para funcionar **sin PC**, solo desde el iPhone.
