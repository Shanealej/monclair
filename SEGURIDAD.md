# Informe de seguridad · Monclair Decants y Perfumes

## Problemas encontrados y cómo se resolvieron

| # | Problema | Por qué era un riesgo | Qué se hizo |
|---|---|---|---|
| 1 | La clave secreta de la app era `papa12`. | Con esa clave alguien puede fabricar una "sesión de administrador" falsa y entrar al panel sin saber la contraseña. | Se usa una clave larga y aleatoria. Si alguien pone una corta, la app crea sola una fuerte y la guarda en un archivo privado (`.secret_key`). |
| 2 | La contraseña del panel era `12345678`. | Es de las primeras que prueban los atacantes. | Contraseña nueva y larga. El panel no se enciende si la contraseña tiene menos de 12 caracteres. |
| 3 | El modo "debug" de Flask estaba siempre encendido. | Si la app queda en internet así, la pantalla de errores deja ejecutar código en el servidor. | Apagado por defecto. Solo se enciende a propósito con `DEBUG=1`, y nunca en internet. |
| 4 | Las fotos se guardaban tal cual llegaban. | Las fotos del celular traen la ubicación GPS y el modelo del teléfono. Además, un archivo disfrazado de foto podía colarse. | Cada foto se abre, se revisa y se guarda una copia nueva y limpia en JPG, sin datos ocultos. Lo que no es una imagen real se rechaza. |
| 5 | El navegador no tenía reglas de protección. | Otra página podía mostrar tu tienda dentro de la suya para engañar, o cargar código ajeno. | Se agregaron cabeceras de seguridad: solo se ejecuta código propio de la tienda, nadie puede enmarcarla, y el panel no se guarda en caché ni aparece en Google. Todo el JavaScript se movió a archivos aparte. |
| 6 | El carrito confiaba en el precio guardado en el navegador. | Si alguien lograba alterar su carrito, podía pedir con precios falsos o cantidades enormes. | Al ver el carrito y al pedir, los precios se vuelven a leer de la base de datos y la cantidad se limita a 20. |
| 7 | Cualquiera podía mandar pedidos sin límite. | Alguien podía llenar tu historial con miles de pedidos falsos. | Máximo 5 pedidos cada 10 minutos por persona. |
| 8 | La sesión del panel no vencía. | Si dejabas el panel abierto en una computadora prestada, quedaba abierto para siempre. | El panel se bloquea al tocar Salir, 30 segundos después de cerrar la pestaña o tras 30 minutos sin uso. La sesión se controla desde el servidor, así que una copia de la cookie deja de servir al salir. |
| 9 | Los intentos de contraseña solo se limitaban por persona. | Varios equipos a la vez podían seguir probando contraseñas. | Además del límite por persona (5), hay un límite general (30 en 15 minutos). Cada intento fallido queda anotado en la terminal. |
| 10 | La confirmación del pedido guardaba todos los datos del cliente en la cookie. | La cookie podía crecer tanto que el navegador la descartaba y el pedido fallaba. | La cookie solo guarda el número del pedido; los datos quedan en el servidor. |
| 11 | Un error de foto muy pesada redirigía a la página anterior. | Se podía usar para mandar a la gente a una página externa. | Ahora siempre vuelve a una página de la propia tienda. |
| 12 | Detalles menores: límites de largo en textos, precios máximos, borrar fotos solo dentro de su carpeta, restar inventario sin quedar en negativo aunque dos personas lo hagan a la vez. | Evitan errores raros y abusos. | Corregidos. |

**Lo que ya estaba bien y se mantuvo:** las consultas a la base de datos son seguras contra "inyección SQL", y los textos se muestran como texto (un `<script>` no se ejecuta). El panel exige un token en cada formulario y la tienda no tiene ningún enlace al panel.

## Cómo se comprobó
Se probaron 43 casos: sesión falsificada con la clave vieja, fotos con GPS, archivos disfrazados, carrito con precio alterado, intentos de inyección, pedidos en masa, bloqueo de contraseña, vencimiento de sesión y todas las páginas. También se revisó en el navegador que no haya errores ni bloqueos.

## Recomendaciones para el futuro
1. **Nunca subas el archivo `.env`, la base de datos (`.db`) ni `.secret_key` a GitHub.** El `.gitignore` ya los excluye.
2. **Cuando la publiques, usa HTTPS** (PythonAnywhere lo da gratis) y pon `PRODUCCION=1` en el `.env`.
3. **Cambia la contraseña del panel cada cierto tiempo** y no la compartas por chat.
4. **Haz copia de la base de datos** (`monclair_shane.db`) y de la carpeta `static/img/subidas` una vez por semana.
5. **El historial guarda nombres, teléfonos y direcciones de clientes.** Descarga el PDF y borra lo viejo cuando ya no lo necesites. No compartas ese PDF.
6. **Actualiza las librerías** de vez en cuando: `pip3 install -U -r requirements.txt`.
7. En internet, usa el servidor del hosting (por ejemplo, el WSGI de PythonAnywhere), no `python3 app.py`.
