# Sistema de Reporte de Incidencias Escolares (ITT)

Solo 3 partes, sin frameworks que instalar:

- `backend/server.py` — API en Python puro (librería estándar: http.server + sqlite3)
- `database/schema.sql` — esquema de la base de datos (usuarios, incidencias)
- `frontend/` — HTML/CSS/JS puro (index, alumno, mantenimiento, admin)

## Cómo correrlo
```bash
# 1. Backend (crea database.db solo, con datos de ejemplo)
cd backend
python3 server.py
# queda escuchando en http://localhost:8000

# 2. Frontend (en otra terminal)
cd frontend
python3 -m http.server 5500
# abre http://localhost:5500 en el navegador
```

## Cuentas de prueba
| Rol           | No. control | Contraseña |
|---------------|-------------|------------|
| Alumno        | 22211616    | 1234       |
| Mantenimiento | M001        | 1234       |
| Administrador | A001        | 1234       |

Ya probé el backend completo con `curl` (login, crear/listar incidencias,
asignar, actualizar avance, resolver, estadísticas, y que cada rol solo
pueda ver/hacer lo que le corresponde) — todo funcionó. El frontend no lo
pude probar en un navegador real (este entorno no tiene uno), pero validé
que el JavaScript no tiene errores de sintaxis y que cada llamada al
backend usa las rutas y campos correctos.

## Si necesitan cambiar a SQL Server más adelante
`server.py` usa `sqlite3` directo. Para cambiar de motor tendrían que
reescribir las funciones de acceso a datos (usa librerías como `pyodbc`) —
el esquema en `schema.sql` ya está en SQL estándar y sirve de base.
