"""Programar y modificar archivos de código desde Jarvis, con VS Code.

Dónde puede trabajar: en la carpeta de proyectos (config.PROJECTS_DIR, por defecto ~/Proyectos) y en las carpetas
que agregues en config_local.py, por ejemplo (para que Jarvis pueda editarse a sí mismo):
    CODIGO_RAICES = [r"C:\\Users\\POWER\\jarvis"]
Para apagar todo esto: PERMISOS = {"codigo": False}

Seguridad integrada:
- Solo toca carpetas de proyectos permitidas; no sale con "..", ni toca Windows ni la carpeta .git.
- Nunca lee ni escribe secretos (.env, credentials.json, token.json, claves .pem/.key...).
- Antes de cambiar o reemplazar un archivo guarda una copia en ~/.jarvis/backups; deshacer_cambio la restaura.
- No ejecuta código: solo lo escribe y lo abre en VS Code.
"""
import difflib, json, os, re, shutil, subprocess, time
from pathlib import Path
import apps_index, config

_ultimo: list = [None]          # último proyecto usado, para "agrégale una función a main.py"
BACKUPS = config.DATA_DIR / "backups"
_INDICE = BACKUPS / "indice.json"
_MAX_ESCRITURA = 200_000        # caracteres por archivo
_IGNORAR = {".git", "node_modules", "__pycache__", ".venv", "venv", "site-packages", "dist", "build", ".idea", ".vscode"}
_NO_ESCRIBIR = {"node_modules", ".venv", "venv", "__pycache__", "site-packages"}
_SECRETOS = re.compile(r"(^\.env($|\.)|credentials.*\.json$|token.*\.json$|client_secret.*\.json$|\.pem$|\.key$|\.pfx$|"
                       r"\.p12$|id_rsa|id_ed25519|\.kdbx$|^secrets?\.)", re.I)
_EXT_PROHIBIDAS = {".exe", ".dll", ".sys", ".msi", ".reg", ".lnk", ".scr", ".com", ".dmp"}
_EXT_CODIGO = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss", ".json", ".md", ".txt", ".yml", ".yaml",
               ".toml", ".ini", ".cfg", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".php", ".rb", ".sh", ".bat",
               ".ps1", ".sql", ".xml", ".vue", ".svelte", ".kt", ".swift", ".lua", ".r", ".ipynb", ".gitignore", ""}


def _permiso():
    if getattr(config, "PERMISOS", {}).get("codigo", True):
        return None
    return "El permiso 'codigo' está desactivado en la configuración (PERMISOS)."


# ------------------------------ Resolución de rutas ------------------------------
def _raices() -> list:
    rs = [config.PROJECTS_DIR] + [Path(x) for x in getattr(config, "CODIGO_RAICES", [])]
    out = []
    for r in rs:
        try:
            r = Path(r).expanduser().resolve()
            if r.is_dir() and r not in out:
                out.append(r)
        except Exception:
            pass
    return out


def _proyectos() -> list:
    """Cada carpeta dentro de PROJECTS_DIR es un proyecto; cada raíz extra cuenta como un proyecto."""
    raices, lista = _raices(), []
    for i, r in enumerate(raices):
        if r == Path(config.PROJECTS_DIR).resolve():
            lista += [d for d in sorted(r.iterdir()) if d.is_dir() and not d.name.startswith(".")]
        else:
            lista.append(r)
    return lista


def _buscar_proyecto(nombre: str):
    q = apps_index._norm(nombre)
    if not q:
        return None
    ps = _proyectos()
    for p in ps:
        if apps_index._norm(p.name) == q:
            return p
    for p in ps:
        if q in apps_index._norm(p.name):
            return p
    mejor = max(ps, key=lambda p: difflib.SequenceMatcher(None, q, apps_index._norm(p.name)).ratio(), default=None)
    if mejor and difflib.SequenceMatcher(None, q, apps_index._norm(mejor.name)).ratio() >= 0.7:
        return mejor
    return None


def _base(proyecto: str):
    if proyecto:
        return _buscar_proyecto(proyecto)
    if _ultimo[0] and Path(_ultimo[0]).is_dir():
        return Path(_ultimo[0])
    ps = _proyectos()
    return max(ps, key=lambda p: p.stat().st_mtime, default=None)


def _resolver(ruta: str = "", proyecto: str = ""):
    """(ruta_absoluta, carpeta_del_proyecto, error)."""
    ruta = (ruta or "").strip().strip('"')
    raices = _raices()
    if not raices:
        return None, None, "No hay carpeta de proyectos. Crea un proyecto primero."
    if ruta and Path(ruta).is_absolute():
        p = Path(ruta).resolve()
        if not any(p == r or r in p.parents for r in raices):
            return None, None, "Esa ruta está fuera de las carpetas de proyectos permitidas (CODIGO_RAICES en la configuración)."
        base = next((pr for pr in _proyectos() if pr == p or pr in p.parents), raices[0])
        _ultimo[0] = base
        return p, base, None
    partes = Path(ruta).parts if ruta else ()
    base = None
    if not proyecto and len(partes) > 1:  # "mi-tienda/index.html"
        cand = _buscar_proyecto(partes[0])
        if cand and apps_index._norm(partes[0]) == apps_index._norm(cand.name):
            base, ruta = cand, str(Path(*partes[1:]))
    if base is None:
        base = _base(proyecto)
    if base is None:
        nombres = ", ".join(p.name for p in _proyectos()[:8]) or "ninguno"
        return None, None, (f"No encuentro el proyecto '{proyecto}'. Proyectos: {nombres}." if proyecto
                            else "No hay ningún proyecto todavía. Crea uno con crear_proyecto.")
    p = (base / ruta).resolve() if ruta else base.resolve()
    base = base.resolve()
    if p != base and base not in p.parents:
        return None, None, "La ruta se sale de la carpeta del proyecto."
    _ultimo[0] = base
    return p, base, None


def _validar(p: Path, escribir: bool):
    """Mensaje de error si Jarvis no debe tocar este archivo, o None."""
    import tools  # import tardío: tools importa este módulo
    partes = {x.lower() for x in p.parts}
    if ".git" in partes:
        return "No toco la carpeta .git; usa subir_cambios para Git."
    if _SECRETOS.search(p.name):
        return "Ese archivo puede tener claves o secretos; por seguridad no lo leo ni lo modifico."
    if tools._bloqueada(p):
        return "Esa ruta es del sistema o está protegida."
    if escribir:
        if partes & _NO_ESCRIBIR:
            return "No escribo dentro de carpetas de dependencias (node_modules, .venv...)."
        if p.suffix.lower() in _EXT_PROHIBIDAS:
            return f"No creo archivos {p.suffix}."
    return None


def _leer_texto(p: Path):
    """(texto, error). Conserva saltos de línea; rechaza binarios y archivos enormes."""
    try:
        if p.stat().st_size > 2_000_000:
            return None, "El archivo es demasiado grande."
        datos = p.read_bytes()
        if b"\x00" in datos[:4096]:
            return None, "Es un archivo binario, no de texto."
        return datos.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, "El archivo no está en UTF-8."
    except Exception as e:
        return None, f"No pude leerlo: {e}"


# ------------------------------ Respaldos ------------------------------
def _indice() -> list:
    try:
        return json.loads(_INDICE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _guardar_indice(lista: list):
    BACKUPS.mkdir(parents=True, exist_ok=True)
    for viejo in lista[:-200]:  # conserva los últimos 200 respaldos
        try:
            if viejo.get("copia"):
                Path(viejo["copia"]).unlink(missing_ok=True)
        except Exception:
            pass
    _INDICE.write_text(json.dumps(lista[-200:], ensure_ascii=False), encoding="utf-8")


def _respaldar(p: Path):
    """Guarda copia del archivo actual (o anota que se creó nuevo) para poder deshacer."""
    BACKUPS.mkdir(parents=True, exist_ok=True)
    lista = _indice()
    copia = None
    if p.exists():
        copia = str(BACKUPS / f"{time.strftime('%Y%m%d-%H%M%S')}-{len(lista):04d}-{p.name}")
        shutil.copy2(p, copia)
    lista.append({"original": str(p), "copia": copia, "ts": time.time()})
    _guardar_indice(lista)


def _vscode(p: Path, linea: int = 0) -> bool:
    if not shutil.which("code"):
        return False
    destino = f"{p}:{int(linea)}" if linea and p.is_file() else str(p)
    flags = "-r -g" if p.is_file() else "-r"
    subprocess.Popen(f'code {flags} "{destino}"', shell=True)
    return True


def _abrir_tras_cambio(p: Path, linea: int = 0) -> str:
    if getattr(config, "CODIGO_ABRIR_VSCODE", True) and _vscode(p, linea):
        return " Lo abrí en VS Code."
    return ""


def _limite_chars() -> int:
    return 5000 if getattr(config, "PROVEEDOR_ACTUAL", "local") == "local" else 14000


def _nl(texto: str, como: str) -> str:
    """Pasa los saltos de línea de 'texto' al estilo de 'como' (CRLF o LF)."""
    t = texto.replace("\r\n", "\n")
    return t.replace("\n", "\r\n") if "\r\n" in como else t


# ------------------------------ Herramientas ------------------------------
def listar_proyecto(proyecto: str = "") -> str:
    """Muestra la estructura de archivos de un proyecto (hasta 3 niveles)."""
    if (m := _permiso()):
        return m
    _p, base, err = _resolver("", proyecto)
    if err:
        return err
    lineas = [f"Proyecto: {base.name}  ({base})"]

    def rec(d: Path, nivel: int):
        try:
            hijos = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except Exception:
            return
        for h in hijos:
            if len(lineas) >= 150:
                return
            if h.name in _IGNORAR or (h.name.startswith(".") and h.name != ".gitignore") or _SECRETOS.search(h.name):
                continue
            lineas.append("  " * nivel + ("[carpeta] " if h.is_dir() else "") + h.name)
            if h.is_dir() and nivel < 3:
                rec(h, nivel + 1)
    rec(base, 1)
    return "\n".join(lineas) + ("\n(lista recortada)" if len(lineas) >= 150 else "")


def leer_codigo(ruta: str, desde: int = 1, hasta: int = 0, proyecto: str = "") -> str:
    """Lee un archivo de código con números de línea (por defecto las primeras 200 líneas)."""
    if (m := _permiso()):
        return m
    p, _b, err = _resolver(ruta, proyecto)
    if err:
        return err
    if (err := _validar(p, False)):
        return err
    if not p.is_file():
        return f"No encuentro el archivo '{ruta}'. Usa listar_proyecto para ver los archivos."
    texto, err = _leer_texto(p)
    if err:
        return err
    lineas = texto.splitlines()
    desde = max(1, int(desde or 1))
    hasta = min(len(lineas), int(hasta) if hasta else desde + 199, desde + 399)
    salida, usados = [], 0
    for i in range(desde, hasta + 1):
        fila = f"{i}: {lineas[i - 1]}"
        usados += len(fila) + 1
        if usados > _limite_chars():
            hasta = i - 1
            break
        salida.append(fila)
    pie = f"\n(líneas {desde}-{hasta} de {len(lineas)})" + (" — hay más, pide otro rango." if hasta < len(lineas) else "")
    return (f"Archivo: {p.name}\n" + "\n".join(salida) + pie) if salida else f"{p.name} está vacío."


def escribir_codigo(ruta: str, contenido: str, sobrescribir: bool = False, proyecto: str = "") -> str:
    """Crea un archivo nuevo con ese contenido. Si ya existe, solo lo reemplaza con sobrescribir=true (guarda respaldo)."""
    if (m := _permiso()):
        return m
    p, base, err = _resolver(ruta, proyecto)
    if err:
        return err
    if not ruta.strip():
        return "Dime el nombre del archivo."
    if (err := _validar(p, True)):
        return err
    if p.suffix.lower() not in _EXT_CODIGO:
        return f"No escribo archivos {p.suffix}; solo de código y texto."
    if len(contenido) > _MAX_ESCRITURA:
        return "El contenido es demasiado grande (máximo 200 000 caracteres)."
    existe = p.exists()
    if p.is_dir():
        return "Esa ruta es una carpeta."
    if existe and not sobrescribir:
        return (f"{p.name} ya existe. Para modificarlo usa editar_codigo (cambios puntuales); "
                "si de verdad quieres reemplazarlo completo, repite con sobrescribir=true.")
    try:
        antes = _leer_texto(p)[0] if existe else ""
        _respaldar(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(_nl(contenido, antes or ""))
    except Exception as e:
        return f"No pude escribir el archivo: {e}"
    return (f"{'Reemplacé' if existe else 'Creé'} {p.relative_to(base)} ({len(contenido.splitlines())} líneas)."
            + _abrir_tras_cambio(p))


def editar_codigo(ruta: str, buscar: str, reemplazar: str, todas: bool = False, proyecto: str = "") -> str:
    """Cambia un fragmento exacto de un archivo. 'buscar' debe aparecer una sola vez (o usa todas=true)."""
    if (m := _permiso()):
        return m
    p, base, err = _resolver(ruta, proyecto)
    if err:
        return err
    if (err := _validar(p, True)):
        return err
    if not p.is_file():
        return f"No encuentro el archivo '{ruta}'."
    if not buscar:
        return "Dime qué fragmento quieres cambiar."
    texto, err = _leer_texto(p)
    if err:
        return err
    b, r = _nl(buscar, texto), _nl(reemplazar, texto)
    n = texto.count(b)
    if n == 0:
        return "No encontré ese fragmento exacto. Lee el archivo con leer_codigo y copia el texto tal cual (con sus espacios)."
    if n > 1 and not todas:
        return (f"Ese fragmento aparece {n} veces. Incluye más líneas alrededor para que sea único, "
                "o usa todas=true si quieres cambiarlas todas.")
    nuevo = texto.replace(b, r) if todas else texto.replace(b, r, 1)
    if len(nuevo) > _MAX_ESCRITURA * 2:
        return "El resultado sería demasiado grande."
    linea = texto[:texto.index(b)].count("\n") + 1
    try:
        _respaldar(p)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(nuevo)
    except Exception as e:
        return f"No pude guardar el cambio: {e}"
    return f"Edité {p.relative_to(base)} ({n if todas else 1} cambio(s), desde la línea {linea})." + _abrir_tras_cambio(p, linea)


def agregar_al_final(ruta: str, contenido: str, proyecto: str = "") -> str:
    """Agrega código al final de un archivo existente (o lo crea si no existe)."""
    if (m := _permiso()):
        return m
    p, base, err = _resolver(ruta, proyecto)
    if err:
        return err
    if (err := _validar(p, True)):
        return err
    if not p.exists():
        return escribir_codigo(ruta, contenido, False, proyecto)
    texto, err = _leer_texto(p)
    if err:
        return err
    if len(texto) + len(contenido) > _MAX_ESCRITURA * 2:
        return "El archivo quedaría demasiado grande."
    try:
        _respaldar(p)
        sep = "" if texto.endswith(("\n", "\r\n")) or not texto else ("\r\n" if "\r\n" in texto else "\n")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(texto + sep + _nl(contenido, texto))
    except Exception as e:
        return f"No pude guardar el cambio: {e}"
    return f"Agregué código al final de {p.relative_to(base)}." + _abrir_tras_cambio(p, len(texto.splitlines()) + 1)


def buscar_en_codigo(consulta: str, proyecto: str = "", extension: str = "") -> str:
    """Busca texto dentro de los archivos de un proyecto (ignora mayúsculas)."""
    if (m := _permiso()):
        return m
    _p, base, err = _resolver("", proyecto)
    if err:
        return err
    q = consulta.strip().lower()
    if not q:
        return "Dime qué texto buscar."
    ext = ("." + extension.strip(".").lower()) if extension else ""
    fin, res = time.time() + 10, []
    for d, subs, archivos in os.walk(base):
        subs[:] = [s for s in subs if s not in _IGNORAR and not s.startswith(".")]
        for nombre in archivos:
            f = Path(d) / nombre
            if _SECRETOS.search(nombre) or f.suffix.lower() not in _EXT_CODIGO or (ext and f.suffix.lower() != ext):
                continue
            texto, e = _leer_texto(f)
            if e:
                continue
            for i, linea in enumerate(texto.splitlines(), 1):
                if q in linea.lower():
                    res.append(f"{f.relative_to(base)}:{i}: {linea.strip()[:140]}")
                    if len(res) >= 40:
                        return "\n".join(res) + "\n(hay más resultados)"
        if time.time() > fin:
            break
    return "\n".join(res) if res else f"No encontré '{consulta}' en {base.name}."


def abrir_en_vscode(ruta: str = "", linea: int = 0, proyecto: str = "") -> str:
    """Abre un proyecto o archivo en Visual Studio Code (opcionalmente en una línea)."""
    if (m := _permiso()):
        return m
    p, _b, err = _resolver(ruta, proyecto)
    if err:
        return err
    if (err := _validar(p, False)):
        return err
    if not p.exists():
        return f"No encuentro '{ruta or proyecto}'."
    if not _vscode(p, int(linea or 0)):
        return "No encuentro el comando 'code'. En VS Code: Ctrl+Shift+P → «Shell Command: Install 'code' command in PATH»."
    return f"Abrí {p.name} en VS Code."


def deshacer_cambio() -> str:
    """Revierte el último cambio hecho por Jarvis en un archivo (restaura la copia guardada)."""
    if (m := _permiso()):
        return m
    lista = _indice()
    if not lista:
        return "No hay cambios que deshacer."
    ult = lista.pop()
    p = Path(ult["original"])
    try:
        if ult.get("copia") and Path(ult["copia"]).exists():
            shutil.copy2(ult["copia"], p)
            Path(ult["copia"]).unlink(missing_ok=True)
            _guardar_indice(lista)
            return f"Restauré la versión anterior de {p.name}." + _abrir_tras_cambio(p)
        if p.exists():  # el archivo lo creó Jarvis: se mueve a la papelera de respaldos, no se borra
            destino = BACKUPS / "eliminados" / f"{time.strftime('%Y%m%d-%H%M%S')}-{p.name}"
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), destino)
        _guardar_indice(lista)
        return f"Quité {p.name}, que había creado yo (queda guardado en ~/.jarvis/backups/eliminados)."
    except Exception as e:
        return f"No pude deshacer el cambio: {e}"


# ------------------------------ Registro para el LLM ------------------------------
def _t(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


S, I, B = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
_PROY = {"type": "string", "description": "Nombre del proyecto; vacío = el último que se usó"}
SPEC = [
    _t("listar_proyecto", "Muestra los archivos de un proyecto de código", {"proyecto": _PROY}, []),
    _t("leer_codigo", "Lee un archivo de código con números de línea. Úsalo ANTES de editar",
       {"ruta": S, "desde": I, "hasta": I, "proyecto": _PROY}, ["ruta"]),
    _t("escribir_codigo", "Crea un archivo de código nuevo con el contenido completo (en la carpeta de proyectos)",
       {"ruta": S, "contenido": S, "sobrescribir": B, "proyecto": _PROY}, ["ruta", "contenido"]),
    _t("editar_codigo", "Modifica un archivo existente reemplazando un fragmento exacto (cambios pequeños y puntuales)",
       {"ruta": S, "buscar": S, "reemplazar": S, "todas": B, "proyecto": _PROY}, ["ruta", "buscar", "reemplazar"]),
    _t("agregar_al_final", "Agrega código al final de un archivo", {"ruta": S, "contenido": S, "proyecto": _PROY}, ["ruta", "contenido"]),
    _t("buscar_en_codigo", "Busca un texto dentro de los archivos de un proyecto", {"consulta": S, "proyecto": _PROY, "extension": S}, ["consulta"]),
    _t("abrir_en_vscode", "Abre un proyecto o archivo en Visual Studio Code", {"ruta": S, "linea": I, "proyecto": _PROY}, []),
    _t("deshacer_cambio", "Revierte el último cambio que hizo Jarvis en un archivo de código", {}, []),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in SPEC}
