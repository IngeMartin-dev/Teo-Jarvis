"""Herramientas que Jarvis puede ejecutar en tu PC."""
import os, subprocess, webbrowser, shutil, re
from datetime import datetime
from pathlib import Path
import config, memory


# ---------- Apps y web ----------
def abrir_app(nombre: str) -> str:
    cmd = config.APPS.get(nombre.lower().strip(), nombre)
    try:
        os.startfile(cmd) if cmd.endswith(":") else subprocess.Popen(f'start "" {cmd}', shell=True)
        return f"Abrí {nombre}."
    except Exception as e:
        return f"No pude abrir {nombre}: {e}"


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
    (carpeta / ".gitignore").write_text("__pycache__/\nnode_modules/\n.env\n", encoding="utf-8")
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


def crear_excel(titulo: str, filas: list[list]) -> str:
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    for f in filas:
        ws.append(f)
    ruta = config.DOCS_DIR / f"{_slug(titulo)}.xlsx"; wb.save(ruta)
    os.startfile(ruta); return f"Excel creado: {ruta}"


def crear_powerpoint(titulo: str, diapositivas: list[dict]) -> str:
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
    """Usa google_calendar.py (ver README para activar OAuth)."""
    try:
        import google_calendar
        return google_calendar.crear_evento(titulo, fecha_hora_iso, duracion_min)
    except ImportError:
        return "Google Calendar aún no está configurado (mira el README, paso 5)."


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
TOOLS_SPEC = [
    _t("abrir_app", "Abre una aplicación de Windows", {"nombre": S}, ["nombre"]),
    _t("abrir_url", "Abre una página web en el navegador", {"url": S}, ["url"]),
    _t("ejecutar_rutina", "Ejecuta una rutina guardada, p. ej. 'inicia mi día'", {"nombre": S}, ["nombre"]),
    _t("crear_proyecto", "Crea un proyecto de código, lo abre en VS Code y crea el repo en GitHub",
       {"nombre": S, "lenguaje": {"type": "string", "enum": ["python", "web", "node"]},
        "publico": {"type": "boolean"}}, ["nombre"]),
    _t("subir_cambios", "Hace commit y push de un proyecto a GitHub", {"proyecto": S, "mensaje": S}, ["proyecto"]),
    _t("crear_word", "Crea un documento Word", {"titulo": S, "contenido": S}, ["titulo", "contenido"]),
    _t("crear_excel", "Crea un Excel; filas es lista de listas",
       {"titulo": S, "filas": {"type": "array", "items": {"type": "array", "items": {}}}}, ["titulo", "filas"]),
    _t("crear_powerpoint", "Crea una presentación PowerPoint",
       {"titulo": S, "diapositivas": {"type": "array", "items": {"type": "object"}}}, ["titulo", "diapositivas"]),
    _t("agendar", "Agenda un evento en Google Calendar (fecha ISO 8601)",
       {"titulo": S, "fecha_hora_iso": S, "duracion_min": {"type": "integer"}}, ["titulo", "fecha_hora_iso"]),
    _t("recordar", "Guarda un dato importante del usuario en memoria", {"texto": S}, ["texto"]),
    _t("olvidar", "Borra recuerdos que contengan el texto", {"texto": S}, ["texto"]),
    _t("hora_actual", "Devuelve fecha y hora actuales", {}, []),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in TOOLS_SPEC}
