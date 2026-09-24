"""
server.py — Backend del Sistema de Reporte de Incidencias Escolares (ITT)

Corre con Python puro: NO necesitas instalar nada (ni FastAPI, ni
SQLAlchemy). Solo usa librerías que ya vienen con Python (http.server,
sqlite3, json).

Cómo correrlo:
    python3 server.py
Por defecto queda escuchando en http://localhost:8000

Base de datos: crea sola database.db (SQLite) la primera vez, usando
../database/schema.sql, y siembra 3 usuarios y 3 incidencias de ejemplo.
"""

import http.server
import socketserver
import sqlite3
import json
import os
import hashlib
import secrets
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

PUERTO = int(os.environ.get("PUERTO", 8000))
RUTA_BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(RUTA_BASE, "database.db")
SCHEMA_PATH = os.path.join(RUTA_BASE, "..", "database", "schema.sql")

# token -> user_id (en memoria; se pierde si reinicias el servidor)
SESIONES = {}


# ----------------------------------------------------------------------
# BASE DE DATOS
# ----------------------------------------------------------------------
def conectar_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def hash_password(password):
    return hashlib.sha256(("itt-incidencias::" + password).encode("utf-8")).hexdigest()


def crear_bd_si_no_existe():
    nueva = not os.path.exists(DB_PATH)
    con = conectar_db()
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        con.executescript(f.read())
    con.commit()

    if nueva or con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        sembrar_datos_ejemplo(con)
    con.close()


def sembrar_datos_ejemplo(con):
    cur = con.cursor()

    def crear_usuario(no_control, nombre, password, rol):
        cur.execute(
            "INSERT INTO usuarios (no_control, nombre, password_hash, rol) VALUES (?,?,?,?)",
            (no_control, nombre, hash_password(password), rol),
        )
        return cur.lastrowid

    alumno_id = crear_usuario("22211616", "Dafne Jael Moguel Benitez", "1234", "alumno")
    mant_id = crear_usuario("M001", "Juan Perez (Mantenimiento)", "1234", "mantenimiento")
    crear_usuario("A001", "Coordinador ITT", "1234", "administrador")

    ahora = datetime.now(timezone.utc).isoformat()

    def crear_incidencia(titulo, desc, ubicacion, categoria, estado="Pendiente",
                          prioridad=None, asignado_a=None, resuelta=False):
        cur.execute(
            """INSERT INTO incidencias
               (folio, titulo, descripcion, ubicacion, categoria, estado, prioridad,
                alumno_id, asignado_a_id, fecha_creacion, fecha_resolucion)
               VALUES ('0000', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (titulo, desc, ubicacion, categoria, estado, prioridad,
             alumno_id, asignado_a, ahora, ahora if resuelta else None),
        )
        nuevo_id = cur.lastrowid
        cur.execute("UPDATE incidencias SET folio=? WHERE id=?", (f"{nuevo_id:04d}", nuevo_id))
        return nuevo_id

    crear_incidencia("Fuga de agua", "Fuga de agua en el pasillo del edificio B, cerca de los baños.",
                      "Edificio B, planta baja", "Infraestructura",
                      estado="En proceso", prioridad="Alta", asignado_a=mant_id)

    crear_incidencia("Lampara fundida", "La lampara del salon 204 no enciende desde hace una semana.",
                      "Edificio A, salon 204", "Electrico")

    crear_incidencia("Puerta de laboratorio dañada", "La chapa de la puerta del laboratorio no cierra bien.",
                      "Edificio C, laboratorio 3", "Seguridad",
                      estado="Resuelto", prioridad="Media", asignado_a=mant_id, resuelta=True)

    con.commit()
    print("Base de datos creada con datos de ejemplo:")
    print("  Alumno:        no_control=22211616  password=1234")
    print("  Mantenimiento: no_control=M001       password=1234")
    print("  Administrador: no_control=A001       password=1234")


# ----------------------------------------------------------------------
# UTILIDADES DE NEGOCIO
# ----------------------------------------------------------------------
def fila_a_incidencia(fila):
    return {
        "id": fila["id"],
        "folio": fila["folio"],
        "titulo": fila["titulo"],
        "descripcion": fila["descripcion"],
        "ubicacion": fila["ubicacion"],
        "categoria": fila["categoria"],
        "estado": fila["estado"],
        "prioridad": fila["prioridad"],
        "notas_avance": fila["notas_avance"],
        "alumno_id": fila["alumno_id"],
        "asignado_a_id": fila["asignado_a_id"],
        "fecha_creacion": fila["fecha_creacion"],
        "fecha_resolucion": fila["fecha_resolucion"],
    }


def calcular_estadisticas(con):
    total = con.execute("SELECT COUNT(*) FROM incidencias").fetchone()[0]
    resueltas = con.execute("SELECT COUNT(*) FROM incidencias WHERE estado='Resuelto'").fetchone()[0]
    pendientes = con.execute("SELECT COUNT(*) FROM incidencias WHERE estado='Pendiente'").fetchone()[0]
    en_proceso = con.execute("SELECT COUNT(*) FROM incidencias WHERE estado='En proceso'").fetchone()[0]

    filas = con.execute(
        "SELECT fecha_creacion, fecha_resolucion FROM incidencias WHERE estado='Resuelto'"
    ).fetchall()
    tiempos = []
    for f in filas:
        if f["fecha_resolucion"]:
            creado = datetime.fromisoformat(f["fecha_creacion"])
            resuelto = datetime.fromisoformat(f["fecha_resolucion"])
            tiempos.append((resuelto - creado).total_seconds() / 86400)
    promedio = round(sum(tiempos) / len(tiempos), 1) if tiempos else None

    return {
        "total": total, "resueltas": resueltas,
        "pendientes": pendientes, "en_proceso": en_proceso,
        "promedio_respuesta_dias": promedio,
    }


# ----------------------------------------------------------------------
# SERVIDOR HTTP
# ----------------------------------------------------------------------
class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, formato, *args):
        print("[server]", formato % args)

    # ---- helpers de respuesta ----
    def enviar_json(self, datos, codigo=200):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(cuerpo)

    def leer_cuerpo_json(self):
        largo = int(self.headers.get("Content-Length", 0))
        if largo == 0:
            return {}
        return json.loads(self.rfile.read(largo).decode("utf-8"))

    def usuario_actual(self, con):
        auth = self.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        user_id = SESIONES.get(token)
        if not user_id:
            return None
        fila = con.execute("SELECT * FROM usuarios WHERE id=?", (user_id,)).fetchone()
        return fila

    def do_OPTIONS(self):
        self.enviar_json({})

    def do_GET(self):
        ruta = urlparse(self.path).path
        con = conectar_db()
        try:
            if ruta == "/incidencias/mias":
                self._ruta_mias(con)
            elif ruta == "/incidencias/asignadas":
                self._ruta_asignadas(con)
            elif ruta == "/admin/bandeja":
                self._ruta_bandeja(con)
            elif ruta == "/admin/personal":
                self._ruta_personal(con)
            elif ruta == "/admin/estadisticas":
                self._ruta_estadisticas(con)
            elif re.fullmatch(r"/incidencias/\d+", ruta):
                self._ruta_detalle(con, int(ruta.split("/")[-1]))
            else:
                self.enviar_json({"error": "Ruta no encontrada"}, 404)
        except Exception as e:
            self.enviar_json({"error": str(e)}, 500)
        finally:
            con.close()

    def do_POST(self):
        ruta = urlparse(self.path).path
        con = conectar_db()
        try:
            if ruta == "/login":
                self._ruta_login(con)
            elif ruta == "/incidencias":
                self._ruta_crear_incidencia(con)
            elif re.fullmatch(r"/incidencias/\d+/avance", ruta):
                self._ruta_avance(con, int(ruta.split("/")[2]))
            elif re.fullmatch(r"/incidencias/\d+/resolver", ruta):
                self._ruta_resolver(con, int(ruta.split("/")[2]))
            elif re.fullmatch(r"/incidencias/\d+/asignar", ruta):
                self._ruta_asignar(con, int(ruta.split("/")[2]))
            else:
                self.enviar_json({"error": "Ruta no encontrada"}, 404)
        except Exception as e:
            self.enviar_json({"error": str(e)}, 500)
        finally:
            con.close()

    # ---- rutas: auth ----
    def _ruta_login(self, con):
        datos = self.leer_cuerpo_json()
        fila = con.execute(
            "SELECT * FROM usuarios WHERE no_control=?", (datos.get("no_control", ""),)
        ).fetchone()
        if not fila or fila["password_hash"] != hash_password(datos.get("password", "")):
            self.enviar_json({"error": "Numero de control o contraseña incorrectos"}, 401)
            return
        token = secrets.token_hex(16)
        SESIONES[token] = fila["id"]
        self.enviar_json({
            "token": token, "rol": fila["rol"], "nombre": fila["nombre"], "user_id": fila["id"],
        })

    # ---- rutas: alumno ----
    def _ruta_mias(self, con):
        usuario = self.usuario_actual(con)
        if not usuario or usuario["rol"] != "alumno":
            self.enviar_json({"error": "No autorizado"}, 401); return
        filas = con.execute(
            "SELECT * FROM incidencias WHERE alumno_id=? ORDER BY id DESC", (usuario["id"],)
        ).fetchall()
        self.enviar_json([fila_a_incidencia(f) for f in filas])

    def _ruta_crear_incidencia(self, con):
        usuario = self.usuario_actual(con)
        if not usuario or usuario["rol"] != "alumno":
            self.enviar_json({"error": "No autorizado"}, 401); return
        datos = self.leer_cuerpo_json()
        ahora = datetime.now(timezone.utc).isoformat()
        cur = con.execute(
            """INSERT INTO incidencias
               (folio, titulo, descripcion, ubicacion, categoria, estado, alumno_id, fecha_creacion)
               VALUES ('0000', ?, ?, ?, ?, 'Pendiente', ?, ?)""",
            (datos.get("titulo", ""), datos.get("descripcion", ""), datos.get("ubicacion", ""),
             datos.get("categoria", ""), usuario["id"], ahora),
        )
        nuevo_id = cur.lastrowid
        con.execute("UPDATE incidencias SET folio=? WHERE id=?", (f"{nuevo_id:04d}", nuevo_id))
        con.commit()
        fila = con.execute("SELECT * FROM incidencias WHERE id=?", (nuevo_id,)).fetchone()
        self.enviar_json(fila_a_incidencia(fila))

    # ---- rutas: detalle (compartida) ----
    def _ruta_detalle(self, con, incidencia_id):
        usuario = self.usuario_actual(con)
        if not usuario:
            self.enviar_json({"error": "No autorizado"}, 401); return
        fila = con.execute("SELECT * FROM incidencias WHERE id=?", (incidencia_id,)).fetchone()
        if not fila:
            self.enviar_json({"error": "No encontrada"}, 404); return
        permitido = (
            usuario["rol"] == "administrador"
            or (usuario["rol"] == "alumno" and fila["alumno_id"] == usuario["id"])
            or (usuario["rol"] == "mantenimiento" and fila["asignado_a_id"] == usuario["id"])
        )
        if not permitido:
            self.enviar_json({"error": "No tienes acceso a esta incidencia"}, 403); return
        self.enviar_json(fila_a_incidencia(fila))

    # ---- rutas: mantenimiento ----
    def _ruta_asignadas(self, con):
        usuario = self.usuario_actual(con)
        if not usuario or usuario["rol"] != "mantenimiento":
            self.enviar_json({"error": "No autorizado"}, 401); return
        filas = con.execute(
            "SELECT * FROM incidencias WHERE asignado_a_id=? AND estado!='Resuelto' ORDER BY id DESC",
            (usuario["id"],),
        ).fetchall()
        self.enviar_json([fila_a_incidencia(f) for f in filas])

    def _ruta_avance(self, con, incidencia_id):
        usuario = self.usuario_actual(con)
        if not usuario or usuario["rol"] != "mantenimiento":
            self.enviar_json({"error": "No autorizado"}, 401); return
        datos = self.leer_cuerpo_json()
        con.execute(
            "UPDATE incidencias SET notas_avance=?, estado=CASE WHEN estado='Pendiente' THEN 'En proceso' ELSE estado END WHERE id=? AND asignado_a_id=?",
            (datos.get("notas_avance", ""), incidencia_id, usuario["id"]),
        )
        con.commit()
        fila = con.execute("SELECT * FROM incidencias WHERE id=?", (incidencia_id,)).fetchone()
        self.enviar_json(fila_a_incidencia(fila))

    def _ruta_resolver(self, con, incidencia_id):
        usuario = self.usuario_actual(con)
        if not usuario or usuario["rol"] != "mantenimiento":
            self.enviar_json({"error": "No autorizado"}, 401); return
        ahora = datetime.now(timezone.utc).isoformat()
        con.execute(
            "UPDATE incidencias SET estado='Resuelto', fecha_resolucion=? WHERE id=? AND asignado_a_id=?",
            (ahora, incidencia_id, usuario["id"]),
        )
        con.commit()
        fila = con.execute("SELECT * FROM incidencias WHERE id=?", (incidencia_id,)).fetchone()
        self.enviar_json(fila_a_incidencia(fila))

    # ---- rutas: administrador ----
    def _ruta_bandeja(self, con):
        usuario = self.usuario_actual(con)
        if not usuario or usuario["rol"] != "administrador":
            self.enviar_json({"error": "No autorizado"}, 401); return
        filas = con.execute("SELECT * FROM incidencias ORDER BY estado ASC, id DESC").fetchall()
        self.enviar_json([fila_a_incidencia(f) for f in filas])

    def _ruta_personal(self, con):
        usuario = self.usuario_actual(con)
        if not usuario or usuario["rol"] != "administrador":
            self.enviar_json({"error": "No autorizado"}, 401); return
        filas = con.execute("SELECT id, no_control, nombre, rol FROM usuarios WHERE rol='mantenimiento'").fetchall()
        self.enviar_json([dict(f) for f in filas])

    def _ruta_asignar(self, con, incidencia_id):
        usuario = self.usuario_actual(con)
        if not usuario or usuario["rol"] != "administrador":
            self.enviar_json({"error": "No autorizado"}, 401); return
        datos = self.leer_cuerpo_json()
        con.execute(
            "UPDATE incidencias SET prioridad=?, asignado_a_id=?, estado=CASE WHEN estado='Pendiente' THEN 'En proceso' ELSE estado END WHERE id=?",
            (datos.get("prioridad"), datos.get("asignado_a_id"), incidencia_id),
        )
        con.commit()
        fila = con.execute("SELECT * FROM incidencias WHERE id=?", (incidencia_id,)).fetchone()
        self.enviar_json(fila_a_incidencia(fila))

    def _ruta_estadisticas(self, con):
        usuario = self.usuario_actual(con)
        if not usuario or usuario["rol"] != "administrador":
            self.enviar_json({"error": "No autorizado"}, 401); return
        self.enviar_json(calcular_estadisticas(con))


class Servidor(socketserver.ThreadingTCPServer):
    allow_reuse_address = True  # evita "Address already in use" al reiniciar rapido


def main():
    crear_bd_si_no_existe()
    with Servidor(("", PUERTO), Handler) as httpd:
        print(f"Servidor corriendo en http://localhost:{PUERTO}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
