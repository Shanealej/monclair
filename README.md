# Monclair Decants y Perfumes

Tienda en Flask + SQLite. Los pedidos se envían por WhatsApp.

## Cómo correrla

```bash
pip3 install -r requirements.txt
python3 app.py
```
Abre http://127.0.0.1:5001

## Panel de administración

1. El usuario y la contraseña están en el archivo `.env` (junto a `app.py`). La contraseña debe tener al menos 12 caracteres.
2. Corre `python3 app.py` y entra a **http://127.0.0.1:5001/admin** (en internet: `tu-pagina.com/admin`).

La tienda no tiene ningún botón hacia el panel. Sin `.env`, `/admin` no existe.

Desde el panel puedes:
- Subir, editar, ocultar o eliminar perfumes (con foto y los 4 precios en dólares).
- Poner descuentos a perfumes, combos y paquetes (porcentaje o precio con descuento) con etiqueta "20% OFF", "Oferta especial" o "Descuento especial".
- Crear combos y paquetes de emprendedor.
- Llevar el inventario: unidades de cada perfume, entradas y salidas. Con 0 unidades el cliente ve "Agotado".
- Poner el precio de envío por barrio y el de transporte fuera de Managua.
- Ver el historial de pedidos y descargarlo en PDF.

## Publicar en internet
Vercel **no sirve** para esta versión: no guarda la base de datos ni las fotos que subes desde el panel.
Usa **PythonAnywhere**, que sí las guarda. Los pasos están en `PUBLICAR.md`.

## Seguridad
Lee `SEGURIDAD.md`. En internet: HTTPS y `PRODUCCION=1` en el `.env`. Nunca `DEBUG=1`.

## Subir a GitHub
El proyecto ya trae Git con el primer commit. Crea un repositorio vacío en github.com y en la terminal escribe:
```bash
git remote add origin https://github.com/TU-USUARIO/monclair.git
git push -u origin main
```
No se suben `.env`, la base de datos ni las fotos subidas (están en `.gitignore`). En otra computadora copia `.env.example` como `.env` y pon tus datos.
