// api.js — compartido por todas las páginas
const API = "http://localhost:8000";

function guardarSesion(datos) {
  localStorage.setItem("sesion", JSON.stringify(datos));
}
function obtenerSesion() {
  const raw = localStorage.getItem("sesion");
  return raw ? JSON.parse(raw) : null;
}
function cerrarSesion() {
  localStorage.removeItem("sesion");
  window.location.href = "index.html";
}

/** Redirige a index.html si no hay sesión, o si el rol no coincide con el de la página. */
function exigirSesion(rolEsperado) {
  const s = obtenerSesion();
  if (!s || (rolEsperado && s.rol !== rolEsperado)) {
    window.location.href = "index.html";
    return null;
  }
  return s;
}

async function apiFetch(ruta, opciones = {}) {
  const s = obtenerSesion();
  const headers = { "Content-Type": "application/json", ...(opciones.headers || {}) };
  if (s) headers["Authorization"] = "Bearer " + s.token;

  const resp = await fetch(API + ruta, { ...opciones, headers });
  let datos = null;
  try { datos = await resp.json(); } catch (e) { /* respuesta vacía */ }

  if (!resp.ok) {
    throw new Error((datos && datos.error) || `Error ${resp.status}`);
  }
  return datos;
}

function badgeEstado(estado) {
  const clase = estado.replace(" ", "-"); // "En proceso" -> "En-proceso" (una sola clase CSS válida)
  return `<span class="badge ${clase}">${estado}</span>`;
}
function badgePrioridad(prioridad) {
  if (!prioridad) return `<span class="badge" style="background:#e2e8f0;color:#64748b">Sin clasificar</span>`;
  return `<span class="badge prioridad-${prioridad}">${prioridad}</span>`;
}
function formatoFecha(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleDateString("es-MX", { day: "2-digit", month: "short", year: "numeric" });
}
