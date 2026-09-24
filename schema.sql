-- Base de datos: Sistema de Reporte de Incidencias Escolares (ITT)
-- SQLite (un solo archivo, cero instalación). El .py que la usa está en
-- backend/server.py y la crea sola la primera vez que se ejecuta.

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no_control TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('alumno', 'mantenimiento', 'administrador'))
);

CREATE TABLE IF NOT EXISTS incidencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folio TEXT UNIQUE NOT NULL,
    titulo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    ubicacion TEXT NOT NULL,
    categoria TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente', 'En proceso', 'Resuelto')),
    prioridad TEXT CHECK (prioridad IN ('Baja', 'Media', 'Alta')),
    notas_avance TEXT,
    alumno_id INTEGER NOT NULL REFERENCES usuarios(id),
    asignado_a_id INTEGER REFERENCES usuarios(id),
    fecha_creacion TEXT NOT NULL,
    fecha_resolucion TEXT
);
