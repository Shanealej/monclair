"""Monclair Decants y Perfumes: tienda en Flask + SQLite con pedidos por WhatsApp y panel de administración."""
import hmac
import os
import re
import secrets
import sqlite3
import time
from functools import wraps
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for

try:  # Pillow limpia las fotos; si no está instalado la tienda igual funciona
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:
    Image = None

CARPETA = Path(__file__).resolve().parent


def cargar_env():
    """Lee el archivo .env (CLAVE=valor)."""
    for ruta in (CARPETA / ".env", CARPETA / ".env.txt"):
        if ruta.is_file():
            for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
                if "=" in linea and not linea.strip().startswith("#"):
                    clave, valor = linea.split("=", 1)
                    os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


cargar_env()



def clave_secreta():
    """Usa SECRET_KEY si es fuerte; si no, crea una aleatoria y la guarda en .secret_key (privado)."""
    clave = os.environ.get("SECRET_KEY", "")
    if len(clave) >= 32:
        return clave
    archivo = CARPETA / ".secret_key"
    if archivo.is_file() and len(archivo.read_text().strip()) >= 32:
        return archivo.read_text().strip()
    clave = secrets.token_urlsafe(48)
    archivo.write_text(clave)
    archivo.chmod(0o600)
    return clave


app = Flask(__name__)
app.secret_key = clave_secreta()
app.config.update(
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,           # fotos de hasta 8 MB
    SESSION_COOKIE_HTTPONLY=True,                 # el JavaScript no puede leer la cookie
    SESSION_COOKIE_SAMESITE="Lax",                # otras páginas no pueden usar tu sesión
    SESSION_COOKIE_SECURE=os.environ.get("PRODUCCION") == "1",  # solo por HTTPS cuando está en internet
)
if Image:
    Image.MAX_IMAGE_PIXELS = 40_000_000
if os.environ.get("PRODUCCION") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)  # IP real del visitante detrás del hosting

# CAMBIAR AQUÍ
NEGOCIO = "Monclair Decants y Perfumes"
WHATSAPP = os.environ.get("WHATSAPP_NUMERO", "50500000000")
ADMIN_USUARIO = os.environ.get("ADMIN_USUARIO", "")
ADMIN_CLAVE = os.environ.get("ADMIN_CLAVE", "")
CLAVE_MINIMA = 12
ADMIN_INACTIVIDAD = 30 * 60    # el panel se bloquea tras 30 minutos sin uso
ADMIN_CIERRE = 30              # segundos para bloquearse después de cerrar la pestaña
MONEDA = "US$"
ENVIO_GRATIS_MAYOR_A = 55     # en dólares
RUTA_BD = CARPETA / "monclair_shane.db"
CARPETA_IMG = CARPETA / "static" / "img"
FOTO_POR_DEFECTO = "monclair_logo.jpeg"

GENEROS = ("Hombre", "Mujer", "Unisex")
FAMILIAS = ("Fresco", "Dulce", "Amaderado", "Floral", "Cítrico")
TAMANOS = {"3": "3 ml", "5": "5 ml", "10": "10 ml", "frasco": "Frasco completo"}
ETIQUETAS_OFERTA = ("% OFF", "Oferta especial", "Descuento especial")
POCAS_UNIDADES = 3
TIPOS_COMBO = {"listo": "Combo", "emprendedor": "Paquete emprendedor"}
CIUDADES = ["Managua", "Estelí", "León", "Granada", "Masaya", "Tipitapa", "Ciudad Sandino", "Chinandega", "Matagalpa", "Otra"]
FORMAS_PAGO = {
    "transferencia": ("Transferencia", "Te pasamos los datos por chat"),
    "pago_movil": ("Pago móvil", "Igual, te lo confirmamos al pedir"),
    "contra_entrega": ("Cuando me llegue", "Si estamos en tu zona"),
}
BARRIOS_INICIALES = ["Altamira", "Villa Fontana", "Carretera a Masaya", "Ciudad Jardín", "Bello Horizonte",
                     "Linda Vista", "Los Robles", "Metrocentro", "Otro barrio de Managua"]
TRANSPORTE = "Fuera de Managua (transporte)"
PAQUETES_INICIALES = [("Paquete inicial", 3, 300), ("Paquete crecimiento", 5, 500), ("Paquete mayorista", 10, 1000)]


# ---------- Base de datos ----------

def conectar_bd():
    conexion = sqlite3.connect(RUTA_BD)
    conexion.row_factory = sqlite3.Row
    return conexion


def consultar(sql, parametros=(), uno=False):
    with conectar_bd() as conexion:
        cursor = conexion.execute(sql, parametros)
        return cursor.fetchone() if uno else cursor.fetchall()


def ejecutar(sql, parametros=()):
    with conectar_bd() as conexion:
        return conexion.execute(sql, parametros).lastrowid


def filas_cambiadas(sql, parametros=()):
    with conectar_bd() as conexion:
        return conexion.execute(sql, parametros).rowcount


def preparar_bd():
    """Crea o actualiza las tablas sin borrar datos."""
    with conectar_bd() as conexion:
        conexion.executescript(f"""
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, marca TEXT NOT NULL,
                genero TEXT NOT NULL, categoria TEXT NOT NULL, precio REAL NOT NULL DEFAULT 0,
                precio_3 REAL NOT NULL DEFAULT 0, precio_5 REAL NOT NULL DEFAULT 0,
                precio_10 REAL NOT NULL DEFAULT 0, precio_frasco REAL NOT NULL DEFAULT 0,
                descripcion TEXT NOT NULL DEFAULT '', imagen TEXT NOT NULL DEFAULT '{FOTO_POR_DEFECTO}',
                activo INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS combos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, precio REAL NOT NULL,
                descripcion TEXT NOT NULL DEFAULT '', imagen TEXT NOT NULL DEFAULT '{FOTO_POR_DEFECTO}',
                activo INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS envios (zona TEXT PRIMARY KEY, precio REAL, transporte INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS ajustes (clave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE IF NOT EXISTS sesiones_admin (id TEXT PRIMARY KEY, visto REAL NOT NULL, cierre REAL);
            CREATE TABLE IF NOT EXISTS inventario (
                id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, producto_id INTEGER,
                producto TEXT NOT NULL, tipo TEXT NOT NULL, cantidad INTEGER NOT NULL,
                existencia INTEGER NOT NULL, nota TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, nombre TEXT NOT NULL,
                telefono TEXT NOT NULL, ciudad TEXT NOT NULL, barrio TEXT NOT NULL, direccion TEXT NOT NULL,
                pago TEXT NOT NULL, productos TEXT NOT NULL, envio TEXT NOT NULL, total TEXT NOT NULL);
        """)
        columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(productos)")}
        for columna, definicion in [("stock", "INTEGER NOT NULL DEFAULT 0"), ("oferta_3", "REAL"), ("oferta_5", "REAL"),
                                    ("oferta_10", "REAL"), ("oferta_frasco", "REAL"), ("descuento", "INTEGER NOT NULL DEFAULT 0"),
                                    ("etiqueta", "TEXT NOT NULL DEFAULT '% OFF'")]:
            if columna not in columnas:
                conexion.execute(f"ALTER TABLE productos ADD COLUMN {columna} {definicion}")
        columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(combos)")}
        for columna, definicion in [("oferta", "REAL"), ("descuento", "INTEGER NOT NULL DEFAULT 0"),
                                    ("etiqueta", "TEXT NOT NULL DEFAULT '% OFF'")]:
            if columna not in columnas:
                conexion.execute(f"ALTER TABLE combos ADD COLUMN {columna} {definicion}")
        if "mensaje" not in {f[1] for f in conexion.execute("PRAGMA table_info(pedidos)")}:
            conexion.execute("ALTER TABLE pedidos ADD COLUMN mensaje TEXT NOT NULL DEFAULT ''")
        if "tipo" not in columnas:
            conexion.execute("ALTER TABLE combos ADD COLUMN tipo TEXT NOT NULL DEFAULT 'listo'")
        if "cantidad" not in columnas:
            conexion.execute("ALTER TABLE combos ADD COLUMN cantidad INTEGER NOT NULL DEFAULT 0")
        if not conexion.execute("SELECT 1 FROM envios LIMIT 1").fetchone():
            conexion.executemany("INSERT INTO envios (zona, precio, transporte) VALUES (?, NULL, 0)", [(b,) for b in BARRIOS_INICIALES])
            conexion.execute("INSERT INTO envios (zona, precio, transporte) VALUES (?, NULL, 1)", (TRANSPORTE,))
        if not conexion.execute("SELECT 1 FROM ajustes WHERE clave = 'paquetes'").fetchone():
            conexion.executemany("INSERT INTO combos (nombre, precio, descripcion, imagen, tipo, cantidad) VALUES (?, ?, '', ?, 'emprendedor', ?)",
                                 [(n, p, FOTO_POR_DEFECTO, c) for n, c, p in PAQUETES_INICIALES])
            conexion.execute("INSERT INTO ajustes (clave, valor) VALUES ('paquetes', 'ok')")


def leer_envios():
    """Devuelve ({barrio: precio}, precio de transporte). None = por confirmar."""
    filas = consultar("SELECT * FROM envios ORDER BY zona")
    barrios = {f["zona"]: f["precio"] for f in filas if not f["transporte"]}
    transporte = next((f["precio"] for f in filas if f["transporte"]), None)
    return barrios, transporte


def combos_publicos(tipo):
    return consultar("SELECT * FROM combos WHERE activo = 1 AND tipo = ? ORDER BY precio", (tipo,))


# ---------- Precios y envío ----------

@app.template_filter("dinero")
def dinero(valor):
    """30 -> 'US$ 30'; 7.5 -> 'US$ 7.50'."""
    valor = float(valor or 0)
    texto = f"{valor:,.0f}" if valor == int(valor) else f"{valor:,.2f}"
    return f"{MONEDA} {texto}"


@app.template_filter("numero")
def numero(valor):
    """Valor para rellenar un campo de precio."""
    if isinstance(valor, (int, float)):
        return f"{valor:g}"
    return valor or ""


@app.template_global()
def precio_final(producto, tamano):
    """Precio con descuento si lo tiene; si no, el normal."""
    return producto[f"oferta_{tamano}"] or producto[f"precio_{tamano}"]


@app.template_global()
def precio_combo(combo):
    return combo["oferta"] or combo["precio"]


@app.template_global()
def etiqueta_oferta(producto):
    """'20% OFF', 'Oferta especial' o 'Descuento especial'; vacío si no tiene descuento."""
    if not producto["descuento"]:
        return ""
    return f"{producto['descuento']}% OFF" if producto["etiqueta"] == "% OFF" else producto["etiqueta"]


def registrar_movimiento(producto_id, producto, tipo, cantidad, existencia, nota=""):
    ejecutar("INSERT INTO inventario (fecha, producto_id, producto, tipo, cantidad, existencia, nota) VALUES (?, ?, ?, ?, ?, ?, ?)",
             (time.strftime("%Y-%m-%d %H:%M"), producto_id, producto, tipo, cantidad, existencia, nota[:120]))


def subtotal(carrito):
    return sum(i["precio"] * i["cantidad"] for i in carrito)


def calcular_envio(carrito, ciudad="", barrio=""):
    """Gratis si supera el monto; si no, precio por barrio (Managua) o transporte (resto)."""
    if subtotal(carrito) > ENVIO_GRATIS_MAYOR_A:
        return {"estado": "gratis", "monto": 0, "tipo": "Envío", "texto": "Gratis"}
    if not ciudad:
        return {"estado": "pendiente", "monto": None, "tipo": "Envío", "texto": "Se calcula según tu ciudad"}
    barrios, transporte = leer_envios()
    if ciudad == "Managua":
        tipo = "Delivery en Managua"
        if barrio not in barrios:
            return {"estado": "pendiente", "monto": None, "tipo": tipo, "texto": "Elige tu barrio"}
        precio = barrios[barrio]
    else:
        tipo, precio = "Cargo de transporte", transporte
    if precio is None:
        return {"estado": "confirmar", "monto": None, "tipo": tipo, "texto": "Por confirmar"}
    return {"estado": "calculado", "monto": precio, "tipo": tipo, "texto": dinero(precio)}


def armar_resumen(carrito, ciudad="", barrio=""):
    envio = calcular_envio(carrito, ciudad, barrio)
    sub = subtotal(carrito)
    return {"subtotal": sub, "envio": envio, "total": sub + (envio["monto"] or 0),
            "faltante": None if envio["estado"] == "gratis" else max(ENVIO_GRATIS_MAYOR_A - sub, 0) + 0.01}


CSP = ("default-src 'self'; img-src 'self' data: blob:; script-src 'self'; style-src 'self'; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


@app.after_request
def cabeceras_seguridad(respuesta):
    """Protecciones del navegador contra scripts ajenos, páginas que te enmarcan y filtraciones."""
    respuesta.headers["Content-Security-Policy"] = CSP
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    respuesta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if app.config["SESSION_COOKIE_SECURE"]:
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000"
    if request.path.startswith("/admin"):
        respuesta.headers["Cache-Control"] = "no-store"
        respuesta.headers["X-Robots-Tag"] = "noindex, nofollow"
    return respuesta


@app.context_processor
def datos_compartidos():
    return {"negocio": NEGOCIO, "whatsapp": WHATSAPP, "moneda": MONEDA, "token": session.get("token", ""),
            "cantidad_carrito": sum(i.get("cantidad", 1) for i in session.get("carrito", []))}


# ---------- Tienda ----------

@app.route("/")
def inicio():
    genero = request.args.get("genero", "").strip()
    categoria = request.args.get("categoria", "").strip()
    busqueda = request.args.get("buscar", "").strip()[:60]
    sql, parametros = "SELECT * FROM productos WHERE activo = 1", []
    if genero in GENEROS:
        sql += " AND genero = ?"
        parametros.append(genero)
    if categoria in FAMILIAS:
        sql += " AND categoria = ?"
        parametros.append(categoria)
    if busqueda:
        sql += " AND (nombre LIKE ? OR marca LIKE ? OR descripcion LIKE ?)"
        parametros += [f"%{busqueda}%"] * 3
    return render_template("index.html", productos=consultar(sql + " ORDER BY marca, nombre", parametros),
                           combos=combos_publicos("listo"), genero=genero, categoria=categoria, buscar=busqueda,
                           hay_perfumes=consultar("SELECT 1 FROM productos WHERE activo = 1 LIMIT 1", uno=True) is not None)


@app.route("/combos")
def ver_combos():
    return render_template("combos.html", combos=combos_publicos("listo"))


@app.route("/emprende")
def emprende():
    return render_template("emprende.html", paquetes=combos_publicos("emprendedor"))


MAX_LINEAS_CARRITO = 15


def agregar_al_carrito(item):
    """Suma una unidad si ya está en el carrito; si no, lo agrega."""
    carrito = session.get("carrito", [])
    for existente in carrito:
        if existente["clave"] == item["clave"]:
            existente["cantidad"] = min(existente["cantidad"] + 1, 20)
            break
    else:
        if len(carrito) < MAX_LINEAS_CARRITO:
            carrito.append({**item, "cantidad": 1})
    session["carrito"] = carrito
    return redirect(url_for("ver_carrito"))


@app.route("/combos/agregar/<int:combo_id>", methods=["POST"])
def agregar_combo(combo_id):
    combo = consultar("SELECT * FROM combos WHERE id = ? AND activo = 1", (combo_id,), uno=True)
    if combo is None:
        abort(404)
    if combo["tipo"] == "emprendedor":
        nombre, marca, tamano = f"{combo['nombre']} ({combo['cantidad']} perfumes)", "Paquete emprendedor", "Frascos completos"
    else:
        nombre, marca, tamano = combo["nombre"], "Combo", "Combo listo"
    return agregar_al_carrito({"clave": f"combo-{combo_id}", "nombre": nombre, "marca": marca, "tamano": tamano,
                               "precio": float(precio_combo(combo))})


@app.route("/pedido/<int:producto_id>", methods=["GET", "POST"])
def pedido(producto_id):
    producto = consultar("SELECT * FROM productos WHERE id = ? AND activo = 1", (producto_id,), uno=True)
    if producto is None:
        abort(404)
    if request.method == "POST":
        tamano = request.form.get("tamano", "3")
        if tamano not in TAMANOS:
            abort(400)
        if producto["stock"] <= 0:
            return redirect(url_for("pedido", producto_id=producto_id))
        return agregar_al_carrito({"clave": f"{producto_id}-{tamano}", "nombre": producto["nombre"], "marca": producto["marca"],
                                   "tamano": TAMANOS[tamano], "precio": float(precio_final(producto, tamano))})
    return render_template("pedido.html", producto=producto)


def carrito_disponible():
    """Revisa el carrito contra la base: precio actual, y quita lo agotado u oculto. Devuelve (carrito, nombres quitados)."""
    carrito, quitados = [], []
    for item in session.get("carrito", []):
        if not isinstance(item, dict) or not isinstance(item.get("clave"), str):
            continue
        cantidad = item["cantidad"] if isinstance(item.get("cantidad"), int) and 1 <= item["cantidad"] <= 20 else 1
        primero, _, segundo = item["clave"].partition("-")
        if primero == "combo" and segundo.isdigit():
            fila = consultar("SELECT precio, oferta FROM combos WHERE id = ? AND activo = 1", (int(segundo),), uno=True)
            precio = precio_combo(fila) if fila else None
        elif primero.isdigit() and segundo in TAMANOS:
            fila = consultar("SELECT * FROM productos WHERE id = ? AND activo = 1 AND stock > 0", (int(primero),), uno=True)
            precio = precio_final(fila, segundo) if fila else None
        else:
            continue
        if precio is None:
            quitados.append(item.get("nombre", "Un producto"))
            continue
        carrito.append({**item, "precio": float(precio), "cantidad": cantidad})
    session["carrito"] = carrito[:MAX_LINEAS_CARRITO]
    return session["carrito"], quitados


def mostrar_carrito(datos, errores=(), codigo=200):
    carrito, quitados = carrito_disponible()
    errores = list(errores) + [f"{n} se agotó y lo quitamos de tu carrito." for n in quitados]
    barrios, transporte = leer_envios()
    return render_template(
        "carrito.html", carrito=carrito, datos=datos, errores=errores, ciudades=CIUDADES, formas_pago=FORMAS_PAGO,
        barrios=list(barrios), envio_gratis_desde=ENVIO_GRATIS_MAYOR_A,
        resumen=armar_resumen(carrito, datos.get("ciudad", ""), datos.get("barrio", "")),
        config_envio={"gratis": subtotal(carrito) > ENVIO_GRATIS_MAYOR_A, "barrios": barrios, "transporte": transporte,
                      "subtotal": subtotal(carrito), "moneda": MONEDA},
    ), codigo


@app.route("/carrito")
def ver_carrito():
    return mostrar_carrito(session.get("datos_cliente", {}))


@app.route("/carrito/eliminar/<clave>", methods=["POST"])
def eliminar_carrito(clave):
    session["carrito"] = [i for i in session.get("carrito", []) if i["clave"] != clave]
    return redirect(url_for("ver_carrito"))


def telefono_valido(texto):
    return 8 <= len(re.sub(r"\D", "", texto)) <= 15


pedidos_por_ip = {}  # ip -> horas de pedidos recientes


def demasiados_pedidos():
    if len(pedidos_por_ip) > 5000:
        pedidos_por_ip.clear()
    ip = request.remote_addr or ""
    recientes = [t for t in pedidos_por_ip.get(ip, []) if time.time() - t < 600]
    pedidos_por_ip[ip] = recientes
    return len(recientes) >= 5


@app.route("/pedido/enviar", methods=["POST"])
def enviar_pedido():
    if demasiados_pedidos():
        return mostrar_carrito(session.get("datos_cliente", {}),
                               ["Hiciste varios pedidos seguidos. Espera unos minutos o escríbenos por WhatsApp."], 429)
    carrito, quitados = carrito_disponible()
    if quitados:
        return mostrar_carrito({}, [f"{n} se agotó y lo quitamos de tu carrito." for n in quitados], 400)
    if not carrito:
        return redirect(url_for("ver_carrito"))
    datos = {campo: request.form.get(campo, "").strip()[:250] for campo in ("nombre", "telefono", "ciudad", "barrio", "direccion", "pago")}
    barrios, _ = leer_envios()
    errores = []
    if len(datos["nombre"]) < 2:
        errores.append("Escribe tu nombre.")
    if not telefono_valido(datos["telefono"]):
        errores.append("Escribe un número de WhatsApp válido.")
    if datos["ciudad"] not in CIUDADES:
        errores.append("Elige tu ciudad.")
    if datos["ciudad"] == "Managua" and datos["barrio"] not in barrios:
        errores.append("Elige tu barrio de Managua para calcular el delivery.")
    if datos["ciudad"] != "Managua":
        datos["barrio"] = ""
    if len(datos["direccion"]) < 5:
        errores.append("Escribe tu dirección y una referencia.")
    if datos["pago"] not in FORMAS_PAGO:
        errores.append("Elige cómo quieres pagar.")
    if errores:
        return mostrar_carrito(datos, errores, 400)

    resumen = armar_resumen(carrito, datos["ciudad"], datos["barrio"])
    envio = resumen["envio"]
    if envio["estado"] == "gratis":
        linea_envio = f"Envío: Gratis (pedido mayor a {dinero(ENVIO_GRATIS_MAYOR_A)})"
    elif envio["estado"] == "confirmar":
        linea_envio = f"{envio['tipo']}: por confirmar"
    else:
        linea_envio = f"{envio['tipo']}: {envio['texto']}"
    total = dinero(resumen["total"]) + (" + envío por confirmar" if envio["estado"] == "confirmar" else "")
    productos = [f"{i['marca']} {i['nombre']} ({i['tamano']}) x{i['cantidad']} - {dinero(i['precio'] * i['cantidad'])}" for i in carrito]
    pago = FORMAS_PAGO[datos["pago"]][0]

    lineas = ["Hola, quiero hacer este pedido:", ""] + [f"• {p}" for p in productos] + [
        "", f"Subtotal: {dinero(resumen['subtotal'])}", linea_envio, f"Total estimado: {total}", "",
        f"Nombre: {datos['nombre']}", f"WhatsApp: {datos['telefono']}", f"Ciudad: {datos['ciudad']}"]
    if datos["barrio"]:
        lineas.append(f"Barrio: {datos['barrio']}")
    lineas += [f"Dirección: {datos['direccion']}", f"Pago: {pago}"]

    # Queda en el historial del panel.
    pedido_id = ejecutar(
        "INSERT INTO pedidos (fecha, nombre, telefono, ciudad, barrio, direccion, pago, productos, envio, total, mensaje) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (time.strftime("%Y-%m-%d %H:%M"), datos["nombre"], datos["telefono"], datos["ciudad"], datos["barrio"],
         datos["direccion"], pago, "\n".join(productos), envio["texto"], total, "\n".join(lineas)))
    pedidos_por_ip.setdefault(request.remote_addr or "", []).append(time.time())

    session["datos_cliente"] = datos
    session["ultimo_pedido"] = pedido_id  # solo el número; los datos quedan en el servidor
    session["carrito"] = []
    return redirect(url_for("pedido_listo"))


@app.route("/pedido/listo")
def pedido_listo():
    pedido_id = session.get("ultimo_pedido")
    pedido_guardado = consultar("SELECT * FROM pedidos WHERE id = ?", (pedido_id,), uno=True) if isinstance(pedido_id, int) else None
    if not pedido_guardado:
        return redirect(url_for("ver_carrito"))
    return render_template("pedido_listo.html", pedido=pedido_guardado,
                           enlace=f"https://wa.me/{WHATSAPP}?text={quote(pedido_guardado['mensaje'])}")


@app.errorhandler(404)
def pagina_no_encontrada(_error):
    return render_template("404.html"), 404


@app.errorhandler(413)
def archivo_grande(_error):
    flash("La foto pesa más de 8 MB. Elige una más liviana.")
    return redirect(url_for("admin_panel") if session.get("admin_sesion") else url_for("inicio"))


@app.errorhandler(400)
@app.errorhandler(500)
def otro_error(error):
    codigo = getattr(error, "code", 500)
    return render_template("error.html", codigo=codigo), codigo


# ---------- Panel de administración ----------

intentos_fallidos = {}  # ip -> horas de intentos fallidos


def panel_activo():
    """El panel solo se enciende con usuario y una contraseña de al menos 12 caracteres."""
    return bool(ADMIN_USUARIO) and len(ADMIN_CLAVE) >= CLAVE_MINIMA


def sesion_admin_valida():
    """La sesión vive en el servidor: se puede cerrar desde aquí aunque el navegador guarde la cookie."""
    sesion_id = session.get("admin_sesion")
    if not isinstance(sesion_id, str):
        return None
    fila = consultar("SELECT * FROM sesiones_admin WHERE id = ?", (sesion_id,), uno=True)
    ahora = time.time()
    if not fila or ahora - fila["visto"] > ADMIN_INACTIVIDAD or (fila["cierre"] and ahora > fila["cierre"]):
        cerrar_sesion_admin()
        return None
    return sesion_id


def cerrar_sesion_admin():
    ejecutar("DELETE FROM sesiones_admin WHERE id = ?", (str(session.get("admin_sesion", "")),))
    for clave in ("admin_sesion", "token"):
        session.pop(clave, None)


def solo_admin(vista):
    """Exige sesión de administrador y, en los POST, el token del formulario."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not panel_activo():
            abort(404)
        sesion_id = sesion_admin_valida()
        if not sesion_id:
            return redirect(url_for("admin_entrar"))
        if request.endpoint == "admin_sigo":  # el aviso automático no cuenta como uso
            ejecutar("UPDATE sesiones_admin SET cierre = NULL WHERE id = ?", (sesion_id,))
        else:
            ejecutar("UPDATE sesiones_admin SET visto = ?, cierre = NULL WHERE id = ?", (time.time(), sesion_id))
        if request.method == "POST" and not hmac.compare_digest(request.form.get("token", ""), session.get("token", "")):
            abort(400)
        return vista(*args, **kwargs)
    return envoltura


@app.route("/admin", methods=["GET", "POST"])
def admin_entrar():
    if not panel_activo():
        abort(404)
    if sesion_admin_valida():
        return redirect(url_for("admin_panel"))
    error = None
    if request.method == "POST":
        ip = request.remote_addr or ""
        ahora = time.time()
        for clave in list(intentos_fallidos):
            intentos_fallidos[clave] = [t for t in intentos_fallidos[clave] if ahora - t < 900]
        total_fallos = sum(len(v) for v in intentos_fallidos.values())
        usuario_ok = hmac.compare_digest(request.form.get("usuario", "").strip().lower()[:60], ADMIN_USUARIO.lower())
        clave_ok = hmac.compare_digest(request.form.get("clave", "")[:200], ADMIN_CLAVE)
        if len(intentos_fallidos.get(ip, [])) >= 5 or total_fallos >= 30:
            error = "Demasiados intentos. Espera 15 minutos."
        elif usuario_ok and clave_ok:
            intentos_fallidos.pop(ip, None)
            carrito = session.get("carrito", [])
            session.clear()  # sesión nueva al entrar
            sesion_id = secrets.token_urlsafe(32)
            ejecutar("DELETE FROM sesiones_admin WHERE visto < ?", (ahora - ADMIN_INACTIVIDAD,))
            ejecutar("INSERT INTO sesiones_admin (id, visto, cierre) VALUES (?, ?, NULL)", (sesion_id, ahora))
            session.update(admin_sesion=sesion_id, token=secrets.token_hex(16), carrito=carrito)
            return redirect(url_for("admin_panel"))
        else:
            intentos_fallidos.setdefault(ip, []).append(ahora)
            app.logger.warning("Intento fallido de entrar al panel desde %s", ip)
            error = "Usuario o contraseña incorrectos."
    return render_template("admin_entrar.html", error=error)


@app.route("/admin/salir", methods=["POST"])
@solo_admin
def admin_salir():
    cerrar_sesion_admin()
    return redirect(url_for("inicio"))


@app.route("/admin/cerrando", methods=["POST"])
@solo_admin
def admin_cerrando():
    """El navegador avisa que se cerró o se fue de la página: si no vuelve en 30 segundos, el panel se bloquea."""
    ejecutar("UPDATE sesiones_admin SET cierre = ? WHERE id = ?", (time.time() + ADMIN_CIERRE, session["admin_sesion"]))
    return "", 204


@app.route("/admin/sigo", methods=["POST"])
@solo_admin
def admin_sigo():
    """La página del panel sigue abierta (lo manda el navegador cada pocos segundos)."""
    return "", 204


@app.route("/admin/panel")
@solo_admin
def admin_panel():
    barrios, transporte = leer_envios()
    return render_template(
        "admin_panel.html", productos=consultar("SELECT * FROM productos ORDER BY marca, nombre"), pocas=POCAS_UNIDADES,
        combos=consultar("SELECT * FROM combos WHERE tipo = 'listo' ORDER BY precio"),
        paquetes=consultar("SELECT * FROM combos WHERE tipo = 'emprendedor' ORDER BY precio"),
        barrios=barrios, transporte=transporte, transporte_zona=TRANSPORTE, envio_gratis=ENVIO_GRATIS_MAYOR_A)


def guardar_foto(archivo):
    """Guarda la foto en static/img/subidas y devuelve su ruta. Lanza ValueError si no es imagen."""
    (CARPETA_IMG / "subidas").mkdir(parents=True, exist_ok=True)
    if Image is None:
        return guardar_foto_sin_pillow(archivo)
    try:
        with Image.open(archivo.stream) as imagen:
            if imagen.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError
            imagen = ImageOps.exif_transpose(imagen).convert("RGB")  # endereza y quita transparencia
            imagen.thumbnail((1600, 1600))
            nombre = f"subidas/{secrets.token_hex(12)}.jpg"
            # Se guarda una copia nueva: sin ubicación GPS ni datos ocultos del archivo original.
            imagen.save(CARPETA_IMG / nombre, "JPEG", quality=85, optimize=True)
    except (ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("La foto debe ser JPG, PNG o WebP.") from None
    return nombre


def guardar_foto_sin_pillow(archivo):
    """Respaldo si falta Pillow: revisa que sea una imagen real, pero no puede quitarle los datos ocultos."""
    datos = archivo.read()
    tipos = {b"\xff\xd8\xff": "jpg", b"\x89PNG\r\n\x1a\n": "png"}
    extension = next((ext for firma, ext in tipos.items() if datos.startswith(firma)), None)
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        extension = "webp"
    if not extension or len(datos) < 1000:
        raise ValueError("La foto debe ser JPG, PNG o WebP.")
    nombre = f"subidas/{secrets.token_hex(12)}.{extension}"
    (CARPETA_IMG / nombre).write_bytes(datos)
    return nombre


def borrar_foto(imagen):
    carpeta = (CARPETA_IMG / "subidas").resolve()
    ruta = (CARPETA_IMG / (imagen or "")).resolve()
    if ruta.parent == carpeta:  # solo borra fotos subidas, nunca otros archivos
        ruta.unlink(missing_ok=True)


def foto_del_formulario(imagen_actual, errores):
    """Si se subió una foto válida la guarda y borra la anterior; si no, deja la actual."""
    foto = request.files.get("foto")
    if errores or not foto or not foto.filename:
        return imagen_actual
    try:
        nueva = guardar_foto(foto)
    except ValueError as error:
        errores.append(str(error))
        return imagen_actual
    borrar_foto(imagen_actual)
    return nueva


def a_numero(texto):
    try:
        valor = float(str(texto).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None
    return round(valor, 2) if 0 < valor <= 100_000 else None


@app.route("/admin/perfume/nuevo", methods=["GET", "POST"])
@app.route("/admin/perfume/<int:producto_id>", methods=["GET", "POST"])
@solo_admin
def admin_perfume(producto_id=None):
    actual = consultar("SELECT * FROM productos WHERE id = ?", (producto_id,), uno=True) if producto_id else None
    if producto_id and actual is None:
        abort(404)
    valores, errores = dict(actual) if actual else {"activo": 1, "imagen": FOTO_POR_DEFECTO}, []
    if request.method == "POST":
        valores = {campo: request.form.get(campo, "").strip() for campo in
                   ("nombre", "marca", "genero", "categoria", "descripcion", "precio_3", "precio_5", "precio_10", "precio_frasco")}
        valores["activo"] = 1 if request.form.get("activo") else 0
        valores["nombre"], valores["marca"] = valores["nombre"][:80], valores["marca"][:60]
        if len(valores["nombre"]) < 2 or len(valores["marca"]) < 2:
            errores.append("Escribe el nombre y la marca.")
        if valores["genero"] not in GENEROS or valores["categoria"] not in FAMILIAS:
            errores.append("Elige para quién es y la familia olfativa.")
        valores.update({c: request.form.get(c, "").strip() for c in ("stock", "descuento", "etiqueta", *[f"oferta_{t}" for t in TAMANOS])})
        precios = [a_numero(valores[f"precio_{t}"]) for t in TAMANOS]
        if None in precios:
            errores.append("Escribe los 4 precios normales en dólares (solo números, por ejemplo 7.50).")
        stock = int(valores["stock"]) if valores["stock"].isdigit() else None
        if stock is None:
            errores.append("Escribe las unidades disponibles (0 si está agotado).")
        ofertas, descuento = descuentos_del_formulario(
            valores, [(f"oferta_{t}", TAMANOS[t], p) for t, p in zip(TAMANOS, precios)], errores)
        etiqueta = valores["etiqueta"] if valores["etiqueta"] in ETIQUETAS_OFERTA else "% OFF"
        valores["imagen"] = foto_del_formulario(actual["imagen"] if actual else FOTO_POR_DEFECTO, errores)
        if not errores:
            fila = (valores["nombre"], valores["marca"], valores["genero"], valores["categoria"], valores["descripcion"][:400],
                    *precios, precios[0], valores["imagen"], valores["activo"], stock, *ofertas, descuento, etiqueta)
            columnas = ("nombre, marca, genero, categoria, descripcion, precio_3, precio_5, precio_10, precio_frasco, precio, "
                        "imagen, activo, stock, oferta_3, oferta_5, oferta_10, oferta_frasco, descuento, etiqueta")
            if actual:
                asignaciones = ", ".join(f"{c.strip()}=?" for c in columnas.split(","))
                ejecutar(f"UPDATE productos SET {asignaciones} WHERE id=?", (*fila, producto_id))
            else:
                producto_id = ejecutar(f"INSERT INTO productos ({columnas}) VALUES ({', '.join('?' * len(fila))})", fila)
            anterior = actual["stock"] if actual else 0
            if stock != anterior:
                registrar_movimiento(producto_id, f"{valores['marca']} {valores['nombre']}", "Entrada" if stock > anterior else "Salida",
                                     abs(stock - anterior), stock, "Inventario inicial" if not actual else "Ajuste al editar el perfume")
            flash("Perfume guardado.")
            return redirect(url_for("admin_panel"))
    return render_template("admin_perfume.html", v=valores, errores=errores, nuevo=actual is None,
                           generos=GENEROS, familias=FAMILIAS, etiquetas=ETIQUETAS_OFERTA)


def descuentos_del_formulario(valores, pares, errores):
    """Calcula los precios con descuento. pares = [(campo, nombre, precio normal)].
    Se puede escribir el porcentaje, los precios con descuento o ambos."""
    texto = valores.get("descuento", "").replace("%", "").strip()
    porcentaje = int(float(texto)) if texto.replace(".", "", 1).isdigit() else 0
    if not 0 <= porcentaje <= 90:
        errores.append("El descuento debe estar entre 0% y 90%.")
        return [None] * len(pares), 0
    ofertas = []
    for campo, nombre, precio in pares:
        escrito = valores.get(campo, "")
        oferta = a_numero(escrito) if escrito else (round(precio * (100 - porcentaje) / 100, 2) if precio and porcentaje else None)
        if escrito and (oferta is None or (precio and oferta >= precio)):
            errores.append(f"El precio con descuento de {nombre} debe ser menor que el precio normal.")
        ofertas.append(oferta)
    if not porcentaje and all(p for _, _, p in pares):
        porcentaje = max((round((p - o) / p * 100) for (_, _, p), o in zip(pares, ofertas) if o), default=0)
    return ofertas, porcentaje


@app.route("/admin/combo/nuevo/<tipo>", methods=["GET", "POST"])
@app.route("/admin/combo/<int:combo_id>", methods=["GET", "POST"])
@solo_admin
def admin_combo(combo_id=None, tipo="listo"):
    actual = consultar("SELECT * FROM combos WHERE id = ?", (combo_id,), uno=True) if combo_id else None
    if (combo_id and actual is None) or tipo not in TIPOS_COMBO:
        abort(404)
    tipo = actual["tipo"] if actual else tipo
    valores, errores = dict(actual) if actual else {"activo": 1, "tipo": tipo, "imagen": FOTO_POR_DEFECTO}, []
    if request.method == "POST":
        valores = {campo: request.form.get(campo, "").strip()
                   for campo in ("nombre", "descripcion", "precio", "cantidad", "oferta", "descuento", "etiqueta")}
        valores.update(tipo=tipo, activo=1 if request.form.get("activo") else 0)
        precio = a_numero(valores["precio"])
        cantidad = int(valores["cantidad"]) if valores["cantidad"].isdigit() else 0
        valores["nombre"] = valores["nombre"][:80]
        if len(valores["nombre"]) < 2:
            errores.append("Escribe el nombre.")
        if precio is None:
            errores.append("Escribe el precio en dólares (solo números).")
        if tipo == "emprendedor" and not 1 <= cantidad <= 500:
            errores.append("Escribe cuántos perfumes trae el paquete.")
        (oferta,), descuento = descuentos_del_formulario(valores, [("oferta", "el combo", precio)], errores)
        etiqueta = valores["etiqueta"] if valores["etiqueta"] in ETIQUETAS_OFERTA else "% OFF"
        valores["imagen"] = foto_del_formulario(actual["imagen"] if actual else FOTO_POR_DEFECTO, errores)
        if not errores:
            fila = (valores["nombre"], precio, valores["descripcion"][:300], valores["imagen"], valores["activo"], tipo, cantidad,
                    oferta, descuento, etiqueta)
            if actual:
                ejecutar("UPDATE combos SET nombre=?, precio=?, descripcion=?, imagen=?, activo=?, tipo=?, cantidad=?, "
                         "oferta=?, descuento=?, etiqueta=? WHERE id=?", (*fila, combo_id))
            else:
                ejecutar("INSERT INTO combos (nombre, precio, descripcion, imagen, activo, tipo, cantidad, oferta, descuento, etiqueta) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", fila)
            flash(f"{TIPOS_COMBO[tipo]} guardado.")
            return redirect(url_for("admin_panel", _anchor="combos"))
    return render_template("admin_combo.html", v=valores, errores=errores, nuevo=actual is None, tipo=tipo,
                           titulo=TIPOS_COMBO[tipo], etiquetas=ETIQUETAS_OFERTA)


@app.route("/admin/<tabla>/<int:registro_id>/eliminar", methods=["POST"])
@solo_admin
def admin_eliminar(tabla, registro_id):
    if tabla not in ("productos", "combos"):
        abort(404)
    fila = consultar(f"SELECT imagen FROM {tabla} WHERE id = ?", (registro_id,), uno=True)
    if fila:
        borrar_foto(fila["imagen"])
        ejecutar(f"DELETE FROM {tabla} WHERE id = ?", (registro_id,))
        flash("Eliminado.")
    return redirect(url_for("admin_panel"))


@app.route("/admin/envios", methods=["POST"])
@solo_admin
def admin_envios():
    for zona in [f["zona"] for f in consultar("SELECT zona FROM envios")]:
        if request.form.get(f"borrar_{zona}"):
            ejecutar("DELETE FROM envios WHERE zona = ? AND transporte = 0", (zona,))
            continue
        ejecutar("UPDATE envios SET precio = ? WHERE zona = ?", (a_numero(request.form.get(f"precio_{zona}", "")), zona))
    nueva = request.form.get("nueva_zona", "").strip()[:60]
    if nueva:
        ejecutar("INSERT OR IGNORE INTO envios (zona, precio, transporte) VALUES (?, ?, 0)",
                 (nueva, a_numero(request.form.get("nuevo_precio", ""))))
    flash("Precios de envío guardados.")
    return redirect(url_for("admin_panel", _anchor="envios"))


@app.route("/admin/inventario", methods=["GET", "POST"])
@solo_admin
def admin_inventario():
    if request.method == "POST":
        producto = consultar("SELECT * FROM productos WHERE id = ?", (request.form.get("producto_id", type=int),), uno=True)
        texto = request.form.get("cantidad", "").strip()
        cantidad = int(texto) if texto.isdigit() and 0 < int(texto) <= 10_000 else 0
        sumar = request.form.get("accion") == "sumar"
        nombre = f"{producto['marca']} {producto['nombre']}" if producto else ""
        if not producto or not cantidad:
            flash("Escribe cuántas unidades (un número mayor que 0).")
            return redirect(url_for("admin_inventario"))
        if sumar:
            filas_cambiadas("UPDATE productos SET stock = stock + ? WHERE id = ?", (cantidad, producto["id"]))
        elif not filas_cambiadas("UPDATE productos SET stock = stock - ? WHERE id = ? AND stock >= ?", (cantidad, producto["id"], cantidad)):
            flash(f"No puedes quitar {cantidad}: de {nombre} solo hay {producto['stock']}.")
            return redirect(url_for("admin_inventario"))
        quedan = consultar("SELECT stock FROM productos WHERE id = ?", (producto["id"],), uno=True)["stock"]
        registrar_movimiento(producto["id"], nombre, "Entrada" if sumar else "Salida", cantidad, quedan,
                             request.form.get("nota", "").strip())
        flash(f"Listo: {nombre} ahora tiene {quedan}.")
        return redirect(url_for("admin_inventario"))
    return render_template("admin_inventario.html", productos=consultar("SELECT * FROM productos ORDER BY marca, nombre"),
                           movimientos=consultar("SELECT * FROM inventario ORDER BY id DESC LIMIT 100"), pocas=POCAS_UNIDADES)


def pedidos_filtrados():
    desde, hasta = request.args.get("desde", ""), request.args.get("hasta", "")
    sql, parametros = "SELECT * FROM pedidos WHERE 1 = 1", []
    if desde:
        sql += " AND fecha >= ?"
        parametros.append(desde)
    if hasta:
        sql += " AND fecha <= ?"
        parametros.append(hasta + " 23:59")
    return consultar(sql + " ORDER BY id DESC", parametros), desde, hasta


@app.route("/admin/historial")
@solo_admin
def admin_historial():
    pedidos, desde, hasta = pedidos_filtrados()
    return render_template("admin_historial.html", pedidos=pedidos, desde=desde, hasta=hasta)


@app.route("/admin/historial.pdf")
@solo_admin
def admin_historial_pdf():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pedidos, desde, hasta = pedidos_filtrados()
    estilos = getSampleStyleSheet()
    celda = estilos["BodyText"]
    celda.fontSize, celda.leading = 8, 10

    def p(texto):
        return Paragraph(str(texto).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>"), celda)

    filas = [["N.º", "Fecha", "Cliente", "Entrega", "Productos", "Envío", "Total"]]
    filas += [[f["id"], f["fecha"], p(f"{f['nombre']}\n{f['telefono']}"), p(f"{f['ciudad']} {f['barrio']}\n{f['direccion']}"),
               p(f["productos"]), p(f["envio"]), p(f["total"])] for f in pedidos]
    tabla = Table(filas, colWidths=[30, 80, 110, 140, 260, 70, 90], repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#05070a")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
    ]))
    periodo = f"Desde {desde or 'el inicio'} hasta {hasta or 'hoy'}"
    salida = BytesIO()
    SimpleDocTemplate(salida, pagesize=landscape(A4), title="Historial de pedidos").build([
        Paragraph(f"{NEGOCIO} · Historial de pedidos", estilos["Title"]),
        Paragraph(f"{periodo} · {len(pedidos)} pedido(s)", estilos["Normal"]), Spacer(1, 10), tabla])
    salida.seek(0)
    return send_file(salida, mimetype="application/pdf", as_attachment=True, download_name="historial_pedidos.pdf")


preparar_bd()

if __name__ == "__main__":
    if Image is None:
        print("\n  Aviso: falta Pillow. Las fotos se guardan sin limpiar. Instálalo con: python3 -m pip install Pillow")
    if panel_activo():
        print("\n  Tienda: http://127.0.0.1:5001\n  Panel:  http://127.0.0.1:5001/admin\n")
    else:
        print(f"\n  Panel apagado: en .env falta ADMIN_USUARIO o ADMIN_CLAVE tiene menos de {CLAVE_MINIMA} caracteres\n")
    app.run(debug=os.environ.get("DEBUG") == "1", port=5001)  # nunca DEBUG=1 en internet
