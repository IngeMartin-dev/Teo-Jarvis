"""Libreta de contactos de Jarvis: contactos.json  (nombre -> whatsapp, correo, discord, alias).

El archivo real es contactos.json (junto al código; Git lo ignora porque tiene datos personales). Si no existe, Jarvis lo crea
copiando contactos.example.json. Edítalo a mano o dile «guarda a Mamá con el número +57 300 123 4567».

Reglas de búsqueda (pensadas para enviar mensajes sin confirmación):
- Coincide el nombre o un alias completo, sin importar mayúsculas ni tildes. Sin adivinar con "se parece a".
- Si el nombre coincide con varios contactos, no se elige ninguno: se pide aclarar.
- Los números que terminan en ceros y los correos @example.com se consideran de ejemplo: no se usan.
- Al consultar contactos, el modelo solo ve los números ocultados y los correos recortados; no se le envía la lista completa.
"""
import json, os, re, shutil
from pathlib import Path
import apps_index, config

_AQUI = Path(__file__).parent
EJEMPLO = _AQUI / "contactos.example.json"
CAMPOS = ("whatsapp", "correo", "discord")
_EMAIL = re.compile(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+")


def archivo() -> Path:
    return Path(getattr(config, "CONTACTOS_FILE", _AQUI / "contactos.json"))


def asegurar_archivo():
    """Crea contactos.json a partir del ejemplo si todavía no existe."""
    f = archivo()
    if not f.exists() and EJEMPLO.exists():
        try:
            shutil.copyfile(EJEMPLO, f)
        except Exception:
            pass


def cargar() -> dict:
    """Devuelve {nombre: datos}. Lanza ValueError con un mensaje claro si el JSON está mal."""
    asegurar_archivo()
    f = archivo()
    if not f.exists():
        return {}
    try:
        datos = json.loads(f.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ValueError(f"contactos.json tiene un error de formato (línea {e.lineno}, columna {e.colno}): {e.msg}. "
                         "Revisa comas y comillas.") from None
    if not isinstance(datos, dict):
        raise ValueError("contactos.json debe ser un objeto con un contacto por nombre.")
    return {k: v for k, v in datos.items() if not k.startswith("_") and isinstance(v, dict)}


def _alias(d: dict) -> list:
    a = d.get("alias", [])
    return [a] if isinstance(a, str) else [x for x in a if isinstance(x, str)]


def _nombres_norm(nombre: str, d: dict) -> set:
    return {apps_index._norm(x) for x in [nombre] + _alias(d) if apps_index._norm(x)}


def es_ejemplo(campo: str, valor: str) -> bool:
    """Números con 7+ ceros seguidos y correos de example.com/.org/.net son de ejemplo."""
    if campo == "whatsapp":
        return bool(re.search(r"0{7,}", re.sub(r"\D", "", valor)))
    if campo == "correo":
        return bool(re.search(r"@(?:[\w-]+\.)*example\.(?:com|org|net)$", valor.strip().lower()))
    return False


def buscar(nombre: str):
    """(nombre_del_contacto, datos, ambiguos). Sin coincidencia: (None, None, [])."""
    q = apps_index._norm(nombre)
    if not q:
        return None, None, []
    contactos = cargar()
    exactos = [n for n, d in contactos.items() if q in _nombres_norm(n, d)]
    if len(exactos) == 1:
        return exactos[0], contactos[exactos[0]], []
    if len(exactos) > 1:
        return None, None, exactos
    qt = set(q.split())
    parciales = [n for n, d in contactos.items()
                 if any(qt <= set(x.split()) for x in _nombres_norm(n, d))]
    if len(parciales) == 1:
        return parciales[0], contactos[parciales[0]], []
    return None, None, parciales


def resolver(nombre: str, campo: str, estricto: bool = False):
    """(valor, error). valor None y error None = no hay contacto/dato (el llamador decide qué hacer).
    estricto=True: si el contacto existe pero no tiene el dato, devuelve un error explicativo."""
    try:
        n, d, amb = buscar(nombre)
    except ValueError as e:
        return None, str(e)
    if amb:
        return None, f"Hay varios contactos que coinciden con «{nombre}»: {', '.join(amb[:6])}. Dime cuál."
    if n is None:
        return (None, f"No tengo a «{nombre}» en contactos.json. Dime su {campo} o guárdalo con guardar_contacto.") if estricto \
            else (None, None)
    valor = str(d.get(campo, "") or "").strip()
    if not valor:
        return (None, f"«{n}» está en tus contactos pero sin {campo}.") if estricto else (None, None)
    if es_ejemplo(campo, valor):
        return None, f"El {campo} de «{n}» en contactos.json todavía es el de ejemplo; cámbialo por el real."
    return valor, None


def correo_guardado(direccion: str) -> bool:
    """¿Esta dirección está en contactos.json? (para permitir el envío sin que el usuario la repita)."""
    try:
        d = direccion.strip().lower()
        return any(str(c.get("correo", "")).strip().lower() == d and not es_ejemplo("correo", d) for c in cargar().values())
    except Exception:
        return False


# ------------------------------ Herramientas ------------------------------
def _ocultar(campo: str, valor: str) -> str:
    if campo == "whatsapp":
        dig = re.sub(r"\D", "", valor)
        return "…" + dig[-3:]
    if campo == "correo":
        u, _, dom = valor.partition("@")
        return (u[:2] + "…@" + dom) if dom else "…"
    return valor


def buscar_contacto(nombre: str = "") -> str:
    """Sin nombre: lista los contactos. Con nombre: dice qué datos tiene (los números salen ocultados)."""
    try:
        if not nombre.strip():
            c = cargar()
            return ("Contactos: " + ", ".join(c)) if c else "No hay contactos guardados todavía."
        n, d, amb = buscar(nombre)
    except ValueError as e:
        return str(e)
    if amb:
        return f"Varios contactos coinciden con «{nombre}»: {', '.join(amb[:6])}."
    if n is None:
        return f"No tengo a «{nombre}» en contactos.json."
    datos = [f"{c}: {_ocultar(c, str(d[c]))}" + (" (de ejemplo)" if es_ejemplo(c, str(d[c])) else "")
             for c in CAMPOS if d.get(c)]
    return f"{n} — " + ("; ".join(datos) if datos else "sin datos todavía.")


def _digitos(s: str) -> str:
    return re.sub(r"\D", "", s)


def guardar_contacto(nombre: str, whatsapp: str = "", correo: str = "", discord: str = "", alias: str = "") -> str:
    """Crea o actualiza un contacto en contactos.json. Los datos deben venir de lo que escribió el usuario."""
    import tools_pc, tools_google
    nombre = nombre.strip()
    if not nombre or len(nombre) > 60 or nombre.startswith("_"):
        return "Dime el nombre del contacto."
    if not any([whatsapp.strip(), correo.strip(), discord.strip(), alias.strip()]):
        return "Dime al menos un dato: whatsapp, correo, discord o alias."
    ctx = tools_google._contexto["texto"]
    nuevos = {}
    if whatsapp.strip():
        if not tools_pc._telefono(whatsapp):
            return "El número no parece válido; escríbelo con indicativo, por ejemplo +57 300 123 4567."
        if _digitos(whatsapp)[-10:] not in _digitos(ctx):
            return "No veo ese número en lo que me dijiste; por seguridad no lo guardo. Dímelo escrito."
        nuevos["whatsapp"] = whatsapp.strip()
    if correo.strip():
        if not _EMAIL.fullmatch(correo.strip()):
            return "El correo no parece válido."
        if correo.strip().lower() not in ctx:
            return "No veo ese correo en lo que me dijiste; por seguridad no lo guardo. Dímelo escrito."
        nuevos["correo"] = correo.strip()
    if discord.strip():
        if discord.strip().lower() not in ctx:
            return "No veo ese usuario de Discord en lo que me dijiste; por seguridad no lo guardo."
        nuevos["discord"] = discord.strip()
    try:
        f = archivo()
        asegurar_archivo()
        crudo = json.loads(f.read_text(encoding="utf-8-sig")) if f.exists() else {}
        existente, d, amb = buscar(nombre)
        if amb:
            return f"Varios contactos coinciden con «{nombre}»: {', '.join(amb[:6])}. Dime el nombre completo."
        clave = existente or nombre
        entrada = crudo.get(clave, {}) if isinstance(crudo.get(clave), dict) else {}
        entrada.update(nuevos)
        if alias.strip():
            lista = entrada.get("alias", [])
            lista = [lista] if isinstance(lista, str) else list(lista)
            entrada["alias"] = lista + [a.strip() for a in alias.split(",") if a.strip() and a.strip() not in lista]
        crudo[clave] = entrada
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(crudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, f)
    except json.JSONDecodeError as e:
        return f"contactos.json tiene un error de formato (línea {e.lineno}); arréglalo antes de guardar contactos."
    except Exception as e:
        return f"No pude guardar el contacto: {e}"
    return f"{'Actualicé' if existente else 'Guardé'} el contacto «{clave}»."


# ------------------------------ Registro para el LLM ------------------------------
def _t(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


S = {"type": "string"}
SPEC = [
    _t("buscar_contacto", "Lista los contactos guardados (sin nombre) o dice qué datos tiene uno. No hace falta para enviar mensajes: "
                          "enviar_whatsapp, enviar_correo y enviar_discord ya buscan el nombre en los contactos", {"nombre": S}, []),
    _t("guardar_contacto", "Guarda o actualiza un contacto (whatsapp con indicativo, correo, usuario de discord, alias separados por coma). "
                           "Solo con datos que el usuario escribió en su mensaje",
       {"nombre": S, "whatsapp": S, "correo": S, "discord": S, "alias": S}, ["nombre"]),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in SPEC}

try:
    asegurar_archivo()
except Exception:
    pass
