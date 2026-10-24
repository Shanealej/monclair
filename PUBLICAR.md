# Publicar Monclair en internet (PythonAnywhere)

## 1. Subir a GitHub
1. Crea un repositorio vacío en github.com (sin README), por ejemplo `monclair`.
2. En la terminal de VS Code, dentro de la carpeta del proyecto:
   ```bash
   git remote add origin https://github.com/TU-USUARIO/monclair.git
   git push -u origin main
   ```
   Si te pide contraseña, GitHub usa un "token": Settings → Developer settings → Personal access tokens.
3. Cada vez que cambies algo:
   ```bash
   git add -A
   git commit -m "describe el cambio"
   git push
   ```

## 2. Crear la página en PythonAnywhere
1. Crea una cuenta en pythonanywhere.com. Tu página quedará en `https://TU-USUARIO.pythonanywhere.com`.
2. Abre **Consoles → Bash** y escribe:
   ```bash
   git clone https://github.com/TU-USUARIO/monclair.git
   cd monclair
   pip3 install --user -r requirements.txt
   cp .env.example .env
   nano .env
   ```
   En `nano` pon tu usuario, tu contraseña (12 o más caracteres), tu WhatsApp y `PRODUCCION=1`. Para `SECRET_KEY` puedes dejarla vacía: la app crea una sola.
   Guarda con **Ctrl + O**, Enter, y sal con **Ctrl + X**.
3. Ve a la pestaña **Web → Add a new web app → Manual configuration →** elige la versión de Python más nueva.
4. En esa misma página:
   - **Source code:** `/home/TU-USUARIO/monclair`
   - **WSGI configuration file:** ábrelo, borra todo y pega:
     ```python
     import sys
     sys.path.insert(0, "/home/TU-USUARIO/monclair")
     from app import app as application
     ```
   - **Static files:** URL `/static/` y carpeta `/home/TU-USUARIO/monclair/static`
   - Activa **Force HTTPS**.
5. Toca el botón verde **Reload**. Abre tu dirección y entra al panel en `/admin`.

## 3. Actualizar la página después de un cambio
En PythonAnywhere, **Consoles → Bash**:
```bash
cd monclair
git pull
```
Luego **Web → Reload**.

## 4. Tu propia dirección (por ejemplo, monclair.com)
- La dirección gratis `TU-USUARIO.pythonanywhere.com` te la crea PythonAnywhere al registrarte.
- Una dirección propia la compras tú en un registrador (Namecheap, GoDaddy, Porkbun; o NIC.ni para `.com.ni`).
- Para usarla en PythonAnywhere necesitas un plan de pago. En la pestaña **Web** agregas tu dominio y te dan un dato **CNAME** que pegas en el registrador.

## Importante
- Las cuentas gratis de PythonAnywhere desactivan la página si pasa un mes sin que entres a renovarla. Entra de vez en cuando y toca el botón de extender.
- Haz copia de `monclair_shane.db` y de `static/img/subidas` (pestaña **Files → Download**).
