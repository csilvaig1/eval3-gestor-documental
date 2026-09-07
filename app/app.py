"""
Gestor Documental - Escuela Basica G-733 Chorombo Bajo
Evaluacion Unidad 3 - Arquitectura de Soluciones Cloud (IF304IINF)
Alvaro Carrasco - Instituto Profesional San Sebastian

Aplicacion web para que el equipo directivo de la escuela cargue, consulte
y descargue la documentacion institucional (memos, oficios, citaciones de
apoderados, acuerdos, documentos de reuniones comunales y permisos).

Los archivos se guardan en Azure Blob Storage y los metadatos en PostgreSQL,
de modo que cualquiera de las instancias de la aplicacion pueda atender la
peticion (requisito para que funcione detras del balanceador de carga).
"""

import os
import socket
import uuid
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (Flask, render_template, request, redirect, url_for,
                   session, send_file, flash, Response)
from azure.storage.blob import BlobServiceClient
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import io
import time

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave-desarrollo-cambiar-en-produccion")

# ---------------------------------------------------------------------------
# Configuracion (se inyecta por variables de entorno desde cloud-init/Ansible)
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "gestordocs")
DB_USER = os.environ.get("DB_USER", "gestor")
DB_PASS = os.environ.get("DB_PASS", "gestor")

BLOB_CONN = os.environ.get("BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER = os.environ.get("BLOB_CONTAINER", "documentos")

# Categorias tomadas literalmente del requerimiento de la directora
# (ver Ficha VcM: memos, oficios, citaciones, acuerdos, reuniones, permisos)
CATEGORIAS = [
    "Memo",
    "Oficio",
    "Citacion de apoderados",
    "Acuerdo de apoderados",
    "Documento de reunion comunal",
    "Permiso administrativo",
]

# Usuarios del equipo directivo. En una version productiva esto iria en la
# base de datos con hash de contrasena; para este proyecto academico se
# mantiene simple y se documenta como mejora pendiente en el informe.
USUARIOS = {
    "directora": os.environ.get("PASS_DIRECTORA", "chorombo2026"),
    "utp": os.environ.get("PASS_UTP", "chorombo2026"),
    "inspectoria": os.environ.get("PASS_INSPECTORIA", "chorombo2026"),
}

# ---------------------------------------------------------------------------
# Metricas para Prometheus
# ---------------------------------------------------------------------------
DOCS_SUBIDOS = Counter("gestordocs_documentos_subidos_total",
                       "Cantidad de documentos subidos", ["categoria"])
DOCS_DESCARGADOS = Counter("gestordocs_documentos_descargados_total",
                           "Cantidad de documentos descargados")
LOGINS_FALLIDOS = Counter("gestordocs_logins_fallidos_total",
                          "Intentos de inicio de sesion fallidos")
LATENCIA = Histogram("gestordocs_duracion_peticion_segundos",
                     "Duracion de las peticiones HTTP", ["endpoint"])


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
def conectar_db():
    """Abre una conexion a PostgreSQL."""
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )


def init_db():
    """Crea la tabla de documentos si todavia no existe.

    Solo se usa para correr la app localmente con "python app.py" (ver el
    bloque main al final del archivo). En Azure el esquema lo crea el
    playbook de Ansible (playbook-servicios.yml), no la aplicacion: bajo
    gunicorn el modulo se carga como "app:app" y el bloque
    "if __name__ == '__main__'" nunca se ejecuta, asi que depender de esta
    funcion en produccion no funcionaria.
    """
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documentos (
                    id SERIAL PRIMARY KEY,
                    nombre_archivo TEXT NOT NULL,
                    nombre_blob TEXT NOT NULL,
                    categoria TEXT NOT NULL,
                    descripcion TEXT,
                    subido_por TEXT NOT NULL,
                    fecha_subida TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """)
            conn.commit()


# ---------------------------------------------------------------------------
# Almacenamiento en Azure Blob
# ---------------------------------------------------------------------------
def cliente_blob():
    """Devuelve el cliente del contenedor de Blob Storage."""
    servicio = BlobServiceClient.from_connection_string(BLOB_CONN)
    return servicio.get_container_client(BLOB_CONTAINER)


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.route("/")
def inicio():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("documentos"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "")
        clave = request.form.get("clave", "")
        if usuario in USUARIOS and USUARIOS[usuario] == clave:
            session["usuario"] = usuario
            return redirect(url_for("documentos"))
        LOGINS_FALLIDOS.inc()
        flash("Usuario o contrasena incorrectos", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/documentos")
def documentos():
    """Lista los documentos cargados, con filtro opcional por categoria."""
    if "usuario" not in session:
        return redirect(url_for("login"))

    inicio_t = time.time()
    filtro = request.args.get("categoria", "")

    with conectar_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if filtro:
                cur.execute(
                    "SELECT * FROM documentos WHERE categoria = %s "
                    "ORDER BY fecha_subida DESC", (filtro,))
            else:
                cur.execute("SELECT * FROM documentos ORDER BY fecha_subida DESC")
            lista = cur.fetchall()

    LATENCIA.labels(endpoint="/documentos").observe(time.time() - inicio_t)
    return render_template("documentos.html", documentos=lista,
                           categorias=CATEGORIAS, filtro=filtro,
                           usuario=session["usuario"],
                           servidor=socket.gethostname())


@app.route("/subir", methods=["POST"])
def subir():
    """Sube un archivo a Blob Storage y guarda sus metadatos en PostgreSQL."""
    if "usuario" not in session:
        return redirect(url_for("login"))

    inicio_t = time.time()
    archivo = request.files.get("archivo")
    categoria = request.form.get("categoria", "")
    descripcion = request.form.get("descripcion", "")

    if not archivo or archivo.filename == "":
        flash("Debe seleccionar un archivo", "error")
        return redirect(url_for("documentos"))

    if categoria not in CATEGORIAS:
        flash("Categoria invalida", "error")
        return redirect(url_for("documentos"))

    # Se genera un nombre unico para evitar que dos archivos con el mismo
    # nombre se sobrescriban entre si dentro del contenedor.
    nombre_blob = f"{uuid.uuid4().hex}_{archivo.filename}"

    contenedor = cliente_blob()
    contenedor.upload_blob(name=nombre_blob, data=archivo.stream, overwrite=False)

    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO documentos
                    (nombre_archivo, nombre_blob, categoria, descripcion, subido_por)
                VALUES (%s, %s, %s, %s, %s)
            """, (archivo.filename, nombre_blob, categoria,
                  descripcion, session["usuario"]))
            conn.commit()

    DOCS_SUBIDOS.labels(categoria=categoria).inc()
    LATENCIA.labels(endpoint="/subir").observe(time.time() - inicio_t)
    flash(f"Documento '{archivo.filename}' cargado correctamente", "ok")
    return redirect(url_for("documentos"))


@app.route("/descargar/<int:doc_id>")
def descargar(doc_id):
    """Descarga un documento desde Blob Storage."""
    if "usuario" not in session:
        return redirect(url_for("login"))

    with conectar_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM documentos WHERE id = %s", (doc_id,))
            doc = cur.fetchone()

    if not doc:
        flash("El documento no existe", "error")
        return redirect(url_for("documentos"))

    contenedor = cliente_blob()
    datos = contenedor.download_blob(doc["nombre_blob"]).readall()

    DOCS_DESCARGADOS.inc()
    return send_file(io.BytesIO(datos), as_attachment=True,
                     download_name=doc["nombre_archivo"])


@app.route("/health")
def health():
    """
    Endpoint que consulta el health probe del balanceador de carga.
    Devuelve 200 solo si la instancia puede hablar con la base de datos,
    de modo que una instancia con la BD caida sea sacada del balanceo.
    """
    try:
        with conectar_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"estado": "ok", "servidor": socket.gethostname()}, 200
    except Exception as e:
        return {"estado": "error", "detalle": str(e)}, 503


@app.route("/metrics")
def metrics():
    """Expone las metricas de la aplicacion para que Prometheus las recolecte."""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000)
