"""Herramientas que Jarvis puede ejecutar en tu PC."""
import base64, io, json, os, re, shutil, subprocess, time, webbrowser
from datetime import datetime
from pathlib import Path
import apps_index, config, memory


# ---------- Apps y web ----------
def abrir_app(nombre: str) -> str:
    cmd = config.APPS.get(nombre.lower().strip())
    try:
        if cmd:
            if cmd.endswith(":"):
                os.startfile(cmd)
            else:
                subprocess.Popen(f'start "" {cmd}', shell=True)
            return f"Abrí {nombre}."
        ok, msg = apps_index.abrir(nombre)
        if ok:
            return msg
        exe = shutil.which(nombre)
        if exe:
            os.startfile(exe)
            return f"Abrí {nombre}."
        return msg + " Si es un sitio web usa abrir_url; si es un archivo o carpeta usa abrir_archivo."
    except Exception as e:
        return f"No pude abrir {nombre}: {e}"


_PROCESOS_SISTEMA = {
    "applicationframehost", "csrss", "dwm", "explorer", "fontdrvhost", "lsass",
    "memory compression", "registry", "runtimebroker", "searchhost", "services",
    "shellexperiencehost", "smss", "spoolsv", "startmenuexperiencehost", "svchost",
    "system", "taskhostw", "wininit", "winlogon",
}


def cerrar_app(nombre: str) -> str:
    """Cierra la app indicada, solo en la sesión del usuario actual; nunca procesos de Windows."""
    q = apps_index._norm(nombre.strip())
    if not q:
        return "Dime qué aplicación quieres cerrar."
    if q in _PROCESOS_SISTEMA:
        return "No puedo cerrar procesos de Windows."
    ps = ("$ErrorActionPreference='SilentlyContinue'; "
          "$sid=(Get-Process -Id $PID).SessionId; "
          "Get-Process | Where-Object {$_.SessionId -eq $sid} "
          "| Select-Object Id,ProcessName,Path,SessionId | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            return "No pude consultar las aplicaciones abiertas."
        data = json.loads(r.stdout.decode("utf-8-sig", "replace") or "[]")
        if isinstance(data, dict):
            data = [data]
    except Exception as e:
        return f"No pude consultar las aplicaciones abiertas: {e}"

    nombres = {q}
    aliases = {"visual studio code": "code", "vscode": "code", "google chrome": "chrome",
               "microsoft edge": "msedge", "bloc de notas": "notepad", "calculadora": "calculatorapp",
               "discord": "discord discordcanary discordptb discorddevelopment"}
    if q in aliases:
        nombres.update(apps_index._norm(aliases[q]).split())
    pids = []
    for p in data:
        proc = apps_index._norm(p.get("ProcessName", ""))
        if proc in _PROCESOS_SISTEMA:
            continue
        ruta = str(p.get("Path") or "").casefold()
        windows = os.environ.get("SystemRoot", r"C:\Windows").casefold().rstrip("\\")
        if ruta and (ruta == windows or ruta.startswith(windows + "\\")):
            continue
        if proc in nombres:
            try:
                pids.append(int(p["Id"]))
            except (KeyError, TypeError, ValueError):
                pass
    if not pids:
        return f"No encontré {nombre} abierta en tu sesión."

    cerrados, errores = 0, []
    for pid in sorted(set(pids)):
        try:
            fin = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                                 text=True, timeout=10,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if fin.returncode == 0:
                cerrados += 1
            else:
                errores.append(fin.stderr.strip() or fin.stdout.strip())
        except Exception as e:
            errores.append(str(e))
    if cerrados:
        return f"Cerré {nombre}."
    return f"No pude cerrar {nombre}: {(errores[0] if errores else 'proceso protegido o sin permisos')[:180]}"


def instalar_app(nombre: str) -> str:
    """Instala por nombre exacto desde WinGet, solo para el usuario actual y sin elevar permisos."""
    nombre = nombre.strip()
    if not nombre or len(nombre) > 100 or any(ord(c) < 32 for c in nombre):
        return "Dime el nombre exacto de la aplicación que quieres instalar."
    winget = shutil.which("winget") or str(Path(os.environ.get("LOCALAPPDATA", "")) /
                                              "Microsoft/WindowsApps/winget.exe")
    if not Path(winget).exists():
        return "No encuentro WinGet. Instala o actualiza 'Instalador de aplicación' desde Microsoft Store."
    cmd = [winget, "install", "--name", nombre, "--exact", "--source", "winget", "--scope", "user",
           "--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=900, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return f"La instalación de {nombre} superó el tiempo límite. Revisa si WinGet sigue trabajando."
    except Exception as e:
        return f"No pude instalar {nombre}: {e}"
    salida = (r.stdout + "\n" + r.stderr).strip()
    if r.returncode == 0:
        try:
            apps_index.cargar(forzar=True)
        except Exception:
            pass
        return f"Instalé {nombre} para tu usuario."
    return (f"No instalé {nombre}. WinGet no encontró una coincidencia exacta, hubo varias, "
            "o el paquete no admite instalación por usuario. No hice una instalación para todo el equipo. "
            + salida[-300:])


def capturar_pantalla() -> str:
    """Captura pantallas actuales en memoria y devuelve JPEG base64; nunca guarda una imagen en disco."""
    try:
        from PIL import ImageGrab
        imagen = ImageGrab.grab(all_screens=True)
        imagen.thumbnail((1600, 1600))
        buffer = io.BytesIO()
        imagen.convert("RGB").save(buffer, format="JPEG", quality=75, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception as e:
        return f"ERROR_CAPTURA: No pude capturar la pantalla: {e}"


def abrir_url(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Abrí {url}"


def ejecutar_rutina(nombre: str) -> str:
    r = config.ROUTINES.get(nombre.lower().strip())
    if not r:
        return f"No tengo la rutina '{nombre}'."
    for u in r.get("urls", []):
        webbrowser.open_new_tab(u)
    for a in r.get("apps", []):
        abrir_app(a)
    return r.get("say", "Rutina ejecutada.")


# ---------- Archivos y carpetas (todo tu PC, menos el sistema) ----------
def _bloqueada(p: Path) -> bool:
    """True si la ruta es del sistema o sensible. Jarvis nunca la toca."""
    try:
        p = p.resolve()
    except Exception:
        return True
    s = str(p).lower()
    raices = [os.environ.get(v, "") for v in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData")]
    prohibidas = [r.lower() for r in raices if r] + [r"c:\$recycle.bin", r"c:\system volume information"]
    if any(s == b or s.startswith(b + os.sep) for b in prohibidas):
        return True
    partes = [x.lower() for x in p.parts]
    return ".ssh" in partes or ".jarvis" in partes or "appdata" in partes


_IGNORAR = {"node_modules", "__pycache__", "venv", ".venv", "site-packages"}


def _buscar(consulta: str, carpeta: str = "", limite: int = 15) -> list:
    tokens = apps_index._norm(consulta).split()
    if not tokens:
        return []
    h = Path.home()
    raices = [Path(carpeta)] if carpeta else (
        [h / d for d in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "OneDrive", "Proyectos")])
    fin, res = time.time() + 10, []
    for raiz in raices:
        if not raiz.exists() or _bloqueada(raiz):
            continue
        for d, subs, archivos in os.walk(raiz):
            subs[:] = [s for s in subs if s not in _IGNORAR and not s.startswith(".") and not _bloqueada(Path(d) / s)]
            for nombre in archivos + subs:
                n = apps_index._norm(nombre)
                if all(t in n for t in tokens):
                    res.append(Path(d) / nombre)
                    if len(res) >= limite:
                        return res
            if time.time() > fin:
                return res
    return res


def buscar_archivos(consulta: str, carpeta: str = "") -> str:
    r = _buscar(consulta, carpeta)
    return "\n".join(map(str, r)) if r else f"No encontré nada que coincida con '{consulta}'."


def abrir_archivo(nombre_o_ruta: str) -> str:
    p = Path(nombre_o_ruta)
    try:
        if p.is_absolute() and p.exists():
            if _bloqueada(p):
                return "Esa ruta es del sistema y no tengo permiso para abrirla."
            os.startfile(p)
            return f"Abrí {p}"
        r = _buscar(nombre_o_ruta)
        if not r:
            return f"No encontré '{nombre_o_ruta}'."
        os.startfile(r[0])
        otros = f" (también hay {len(r) - 1} coincidencias más)" if len(r) > 1 else ""
        return f"Abrí {r[0]}{otros}"
    except Exception as e:
        return f"No pude abrirlo: {e}"


def listar_carpeta(ruta: str) -> str:
    p = Path(ruta)
    if not p.is_absolute():
        p = Path.home() / ruta
    if _bloqueada(p) or not p.is_dir():
        return "No puedo listar esa carpeta."
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))[:60]
    return "\n".join(("[carpeta] " if i.is_dir() else "") + i.name for i in items) or "(vacía)"


def leer_archivo(ruta: str, max_caracteres: int = 4000) -> str:
    p = Path(ruta)
    if not p.is_absolute():
        r = _buscar(ruta)
        if not r:
            return f"No encontré '{ruta}'."
        p = r[0]
    if _bloqueada(p) or not p.is_file():
        return "No puedo leer ese archivo."
    try:
        if p.suffix.lower() == ".docx":
            from docx import Document
            texto = "\n".join(x.text for x in Document(p).paragraphs)
        else:
            texto = p.read_text(encoding="utf-8", errors="replace")
        return texto[:max_caracteres] or "(vacío)"
    except Exception as e:
        return f"No pude leerlo: {e}"


def crear_carpeta(ruta: str) -> str:
    p = Path(ruta)
    if not p.is_absolute():
        p = Path.home() / ruta
    if _bloqueada(p):
        return "No puedo crear carpetas ahí."
    p.mkdir(parents=True, exist_ok=True)
    return f"Carpeta lista: {p}"


# ---------- Programación ----------
def _slug(n: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", n.strip()).strip("-").lower()


def crear_proyecto(nombre: str, lenguaje: str = "python", publico: bool = False) -> str:
    """Crea carpeta + archivos base, abre VS Code, git init y repo en GitHub (requiere gh CLI)."""
    carpeta = config.PROJECTS_DIR / _slug(nombre)
    carpeta.mkdir(exist_ok=True)
    if lenguaje.lower() in ("python", "py"):
        (carpeta / "main.py").write_text('print("Hola desde ' + nombre + '")\n', encoding="utf-8")
        (carpeta / "requirements.txt").write_text("", encoding="utf-8")
    elif lenguaje.lower() in ("web", "html"):
        (carpeta / "index.html").write_text(
            f"<!doctype html><html><head><meta charset='utf-8'><title>{nombre}</title>"
            "<link rel='stylesheet' href='style.css'></head><body><h1>"
            f"{nombre}</h1><script src='app.js'></script></body></html>", encoding="utf-8")
        (carpeta / "style.css").write_text("body{font-family:sans-serif}\n", encoding="utf-8")
        (carpeta / "app.js").write_text("console.log('listo');\n", encoding="utf-8")
    elif lenguaje.lower() in ("node", "js"):
        (carpeta / "index.js").write_text("console.log('listo');\n", encoding="utf-8")
    (carpeta / "README.md").write_text(f"# {nombre}\n", encoding="utf-8")
    (carpeta / ".gitignore").write_text("__pycache__/\nnode_modules/\n.venv/\n.env\n", encoding="utf-8")
    subprocess.Popen(f'code "{carpeta}"', shell=True)
    msg = f"Proyecto creado en {carpeta} y abierto en VS Code."
    if shutil.which("git"):
        subprocess.run(["git", "init"], cwd=carpeta, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=carpeta, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Commit inicial"], cwd=carpeta, capture_output=True)
        if shutil.which("gh"):
            vis = "--public" if publico else "--private"
            r = subprocess.run(["gh", "repo", "create", _slug(nombre), vis, "--source", ".", "--push"],
                               cwd=carpeta, capture_output=True, text=True)
            msg += " Repo de GitHub creado y subido." if r.returncode == 0 else f" GitHub falló: {r.stderr.strip()[:200]}"
        else:
            msg += " (Instala GitHub CLI 'gh' y haz 'gh auth login' para crear repos.)"
    return msg


def subir_cambios(proyecto: str, mensaje: str = "") -> str:
    carpeta = config.PROJECTS_DIR / _slug(proyecto)
    if not carpeta.exists():
        return f"No encuentro el proyecto {proyecto}."
    mensaje = mensaje or f"Actualización {datetime.now():%Y-%m-%d %H:%M}"
    subprocess.run(["git", "add", "."], cwd=carpeta)
    subprocess.run(["git", "commit", "-m", mensaje], cwd=carpeta, capture_output=True)
    r = subprocess.run(["git", "push"], cwd=carpeta, capture_output=True, text=True)
    return "Cambios subidos a GitHub." if r.returncode == 0 else f"Error al subir: {r.stderr.strip()[:200]}"


# ---------- Documentos ----------
def crear_word(titulo: str, contenido: str) -> str:
    from docx import Document
    d = Document(); d.add_heading(titulo, 0)
    for p in contenido.split("\n"):
        d.add_paragraph(p)
    ruta = config.DOCS_DIR / f"{_slug(titulo)}.docx"; d.save(ruta)
    os.startfile(ruta); return f"Documento creado: {ruta}"


def crear_excel(titulo: str, filas: list) -> str:
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    for f in filas:
        ws.append(f)
    ruta = config.DOCS_DIR / f"{_slug(titulo)}.xlsx"; wb.save(ruta)
    os.startfile(ruta); return f"Excel creado: {ruta}"


def agregar_fila_excel(valores: list, archivo: str = "agenda.xlsx") -> str:
    """Agrega una fila a un Excel existente (o lo crea). Útil como agenda/registro."""
    from openpyxl import Workbook, load_workbook
    ruta = config.DOCS_DIR / (archivo if archivo.lower().endswith(".xlsx") else archivo + ".xlsx")
    try:
        wb = load_workbook(ruta) if ruta.exists() else Workbook()
        wb.active.append(valores)
        wb.save(ruta)
        return f"Fila agregada en {ruta.name}."
    except PermissionError:
        return f"No pude guardar: cierra {ruta.name} en Excel y vuelve a intentarlo."


def crear_powerpoint(titulo: str, diapositivas: list) -> str:
    """diapositivas: [{"titulo": "...", "puntos": ["...", "..."]}]"""
    from pptx import Presentation
    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[0]); s.shapes.title.text = titulo
    for d in diapositivas:
        s = p.slides.add_slide(p.slide_layouts[1]); s.shapes.title.text = d.get("titulo", "")
        tf = s.placeholders[1].text_frame; tf.text = ""
        for i, pt in enumerate(d.get("puntos", [])):
            (tf.paragraphs[0] if i == 0 else tf.add_paragraph()).text = pt
    ruta = config.DOCS_DIR / f"{_slug(titulo)}.pptx"; p.save(ruta)
    os.startfile(ruta); return f"Presentación creada: {ruta}"


# ---------- Calendario (Google) ----------
def agendar(titulo: str, fecha_hora_iso: str, duracion_min: int = 60) -> str:
    try:
        import google_calendar
        return google_calendar.crear_evento(titulo, fecha_hora_iso, duracion_min)
    except ImportError:
        return "Faltan las librerías de Google. Ejecuta: python -m pip install -r requirements.txt"
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"No pude agendar: {e}"


def ver_agenda(cantidad: int = 5) -> str:
    try:
        import google_calendar
        return google_calendar.proximos(cantidad)
    except ImportError:
        return "Faltan las librerías de Google. Ejecuta: python -m pip install -r requirements.txt"
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"No pude leer la agenda: {e}"


# ---------- Memoria ----------
def recordar(texto: str) -> str: return memory.recordar(texto)
def olvidar(texto: str) -> str: return memory.olvidar(texto)


def hora_actual() -> str:
    return datetime.now().strftime("%A %d de %B de %Y, %H:%M")


# ---------- Registro para el LLM ----------
def _t(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}

S = {"type": "string"}
I = {"type": "integer"}
TOOLS_SPEC = [
    _t("abrir_app", "Abre cualquier aplicación o juego instalado en el PC por su nombre (Roblox, Spotify, Steam, Discord...)", {"nombre": S}, ["nombre"]),
    _t("cerrar_app", "Cierra la aplicación indicada si está abierta. Usa esto solo cuando el usuario pida cerrar esa aplicación. No cierra procesos de Windows.", {"nombre": S}, ["nombre"]),
    _t("instalar_app", "Instala la aplicación que el usuario pidió explícitamente, desde WinGet, solo para su usuario. No instala paquetes de sistema ni ejecuta comandos arbitrarios.", {"nombre": S}, ["nombre"]),
    _t("abrir_url", "Abre una página web en el navegador", {"url": S}, ["url"]),
    _t("ejecutar_rutina", "Ejecuta una rutina guardada, p. ej. 'inicia mi día'", {"nombre": S}, ["nombre"]),
    _t("abrir_archivo", "Abre un archivo o carpeta del PC por nombre o ruta completa", {"nombre_o_ruta": S}, ["nombre_o_ruta"]),
    _t("buscar_archivos", "Busca archivos o carpetas por nombre en el PC", {"consulta": S, "carpeta": S}, ["consulta"]),
    _t("listar_carpeta", "Lista el contenido de una carpeta", {"ruta": S}, ["ruta"]),
    _t("leer_archivo", "Lee el texto de un archivo (txt, código, docx...)", {"ruta": S}, ["ruta"]),
    _t("crear_carpeta", "Crea una carpeta", {"ruta": S}, ["ruta"]),
    _t("crear_proyecto", "Crea un proyecto de código, lo abre en VS Code y crea el repo en GitHub",
       {"nombre": S, "lenguaje": {"type": "string", "enum": ["python", "web", "node"]},
        "publico": {"type": "boolean"}}, ["nombre"]),
    _t("subir_cambios", "Hace commit y push de un proyecto a GitHub", {"proyecto": S, "mensaje": S}, ["proyecto"]),
    _t("crear_word", "Crea un documento Word", {"titulo": S, "contenido": S}, ["titulo", "contenido"]),
    _t("crear_excel", "Crea un Excel nuevo; filas es lista de listas",
       {"titulo": S, "filas": {"type": "array", "items": {"type": "array", "items": {}}}}, ["titulo", "filas"]),
    _t("agregar_fila_excel", "Agrega una fila a un Excel existente (por defecto agenda.xlsx)",
       {"valores": {"type": "array", "items": {}}, "archivo": S}, ["valores"]),
    _t("crear_powerpoint", "Crea una presentación PowerPoint",
       {"titulo": S, "diapositivas": {"type": "array", "items": {"type": "object"}}}, ["titulo", "diapositivas"]),
    _t("agendar", "Agenda un evento en Google Calendar (fecha ISO 8601, ej. 2026-11-22T15:00:00)",
       {"titulo": S, "fecha_hora_iso": S, "duracion_min": I}, ["titulo", "fecha_hora_iso"]),
    _t("ver_agenda", "Muestra los próximos eventos de Google Calendar", {"cantidad": I}, []),
    _t("recordar", "Guarda un dato importante del usuario en memoria", {"texto": S}, ["texto"]),
    _t("olvidar", "Borra recuerdos que contengan el texto", {"texto": S}, ["texto"]),
    _t("hora_actual", "Devuelve fecha y hora actuales", {}, []),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in TOOLS_SPEC}


# ---------- Google: Gmail, Drive y plan del día ----------
import tools_google
TOOLS_SPEC += tools_google.SPEC
REGISTRY.update(tools_google.REGISTRY)

# ---------- PC: Microsoft Store, mouse/teclado y WhatsApp ----------
import tools_pc
TOOLS_SPEC += tools_pc.SPEC
REGISTRY.update(tools_pc.REGISTRY)

# ---------- Programar y modificar código (VS Code) ----------
import tools_codigo
TOOLS_SPEC += tools_codigo.SPEC
REGISTRY.update(tools_codigo.REGISTRY)


# ---------- Selección de herramientas por tema (menos tokens = respuestas más rápidas) ----------
_BASE = {"abrir_app", "cerrar_app", "instalar_app", "buscar_en_tienda", "instalar_desde_tienda", "abrir_tienda",
         "abrir_url", "ejecutar_rutina", "recordar", "olvidar", "hora_actual"}
_GRUPOS = [
    (("correo", "mail", "gmail", "drive", "agenda", "calendar", "calendario", "reunión", "reunion",
      "evento", "agend", "plan", "cita", "envía", "envia", "enviar"),
     {"ver_correos", "leer_correo", "enviar_correo", "confirmar_envio", "cancelar_envio", "plan_del_dia",
      "buscar_en_drive", "drive_recientes", "leer_drive", "subir_a_drive", "agendar", "ver_agenda"}),
    (("archivo", "carpeta", "documento", "busca", "encuentra", "lee ", "lista", "descargas", "escritorio",
      "foto", "imagen", "pdf", "abre el", "abre mi"),
     {"abrir_archivo", "buscar_archivos", "listar_carpeta", "leer_archivo", "crear_carpeta"}),
    (("word", "excel", "powerpoint", "presentación", "presentacion", "diapositiva", "tabla", "planilla", "fila"),
     {"crear_word", "crear_excel", "agregar_fila_excel", "crear_powerpoint"}),
    (("proyecto", "repositorio", "github", "git", "sube", "código", "codigo", "programar", "commit"),
     {"crear_proyecto", "subir_cambios"}),
    (("programa", "código", "codigo", "vsc", "vs code", "visual studio", "edita", "edítalo", "editalo", "modifica",
      "modifícalo", "modificalo", "agrega", "agrégale", "agregale", "añade", "añádele", "función", "funcion", "clase",
      "bug", "corrige", "arregla", "refactor", "script", "archivo", ".py", ".js", ".html", ".css", ".json", ".ts"),
     {"listar_proyecto", "leer_codigo", "escribir_codigo", "editar_codigo", "agregar_al_final", "buscar_en_codigo",
      "abrir_en_vscode", "deshacer_cambio", "crear_proyecto", "subir_cambios"}),
    (("tienda", "store", "instala", "descarga", "descargar"),
     {"abrir_tienda", "buscar_en_tienda", "instalar_desde_tienda"}),
    (("whatsapp", "wasap", "mensaje a", "mándale", "mandale", "escríbele", "escribele", "dile a"),
     {"enviar_whatsapp", "confirmar_whatsapp", "cancelar_whatsapp"}),
    (("mouse", "ratón", "raton", "clic", "click", "haz clic", "teclado", "escribe", "teclea", "tecla", "scroll",
      "desplaza", "botón", "boton", "pulsa", "presiona", "controla", "pestaña", "ventana", "cursor"),
     {"tamano_pantalla", "listar_elementos", "clic_elemento", "mover_mouse", "clic", "scroll",
      "escribir_texto", "presionar_teclas"}),
]


def seleccionar(texto: str) -> list:
    """Devuelve solo las herramientas relevantes para el mensaje."""
    t = texto.lower()
    nombres = set(_BASE)
    for palabras, grupo in _GRUPOS:
        if any(p in t for p in palabras):
            nombres |= grupo
    if tools_google._pendiente:   # hay un correo esperando confirmación
        nombres |= {"confirmar_envio", "cancelar_envio", "enviar_correo"}
    if tools_pc._wa:              # hay un WhatsApp esperando confirmación
        nombres |= {"confirmar_whatsapp", "cancelar_whatsapp"}
    return [f for f in TOOLS_SPEC if f["function"]["name"] in nombres]
