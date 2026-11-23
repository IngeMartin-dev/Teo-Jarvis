"""Enviar mensajes a Discord desde Jarvis. SE ENVÍAN DE INMEDIATO, sin pedir confirmación.

Los destinos están en su propio archivo, discord.json (junto al código; Git lo ignora). Si no existe, Jarvis lo crea copiando
discord.example.json. Estructura:
    {"usuarios": {"Mamá": {"alias": ["mami"], "usuario": "mama_usuario"}},
     "canales":  {"general": {"servidor": "Mi Servidor", "webhook": "https://discord.com/api/webhooks/..."}}}

Alias: lo que tú dices («bolso», «Sala 1») es solo un nombre para elegir la entrada; a Discord SIEMPRE se le busca el nombre real:
  usuario → campo "usuario" (y "nombre" / "nombre_visible" = cómo se ve en el chat, para verificar); canal o sala → campo "nombre" (o la clave).
  Ej.: "Sala 1": {"nombre": "general", "servidor": "Mi Servidor"} → «únete a sala uno» entra al canal de voz «general».

Usuarios: el usuario exacto (@weon07865) es único, así que si no pones «nombre_visible» Jarvis no comprueba el título (los nombres
decorados no se leen bien en la ventana). Si pones «nombre_visible», sí comprueba que el chat abierto lo muestre.

Cómo se envía:
- Canal con "webhook": directo por internet, sin abrir Discord (lo más fiable; los mensajes salen sin menciones @everyone/@usuario).
- Usuario, o canal sin webhook: por Discord Desktop (Ctrl+K). Antes de escribir comprueba por el título de la ventana que se abrió el
  chat correcto (y el servidor, si lo indicaste); si no puede comprobarlo, NO envía.
- Si el nombre no está en discord.json se intenta igual (webhook DISCORD_WEBHOOK_<NOMBRE> del .env o búsqueda directa en Discord).

Llamadas: unirse_llamada_discord(sala) entra a un canal de voz por su nombre (Ctrl+K con «!»). Las salas pueden listarse en la sección
«salas» de discord.json ({"Sala 1": {"servidor": "Mi Servidor", "alias": [...]}}), pero no es obligatorio.

Opciones (config_local.py): PERMISOS = {"discord": False} lo apaga; DISCORD_VERIFICAR_TITULO = False desactiva la comprobación del
título (solo si tu Discord no muestra el nombre del chat en la ventana).
"""
import json, os, re, shutil, time, unicodedata
from pathlib import Path
import requests
import difflib
import apps_index, config

_NUM = {"cero": "0", "uno": "1", "una": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5",
        "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10"}


def _n(x: str) -> str:
    """Normaliza para comparar: sin mayúsculas ni tildes, y «sala uno» = «sala 1»."""
    x = unicodedata.normalize("NFKD", str(x))   # letras decorativas (𝔦𝔫𝔦𝔨𝔬, ｉｎｉｋｏ) -> normales
    return " ".join(_NUM.get(p, p) for p in apps_index._norm(x).split())

_AQUI = Path(__file__).parent
EJEMPLO = _AQUI / "discord.example.json"
_HOOK = re.compile(r"^https://(?:ptb\.|canary\.)?(?:discord|discordapp)\.com/api/webhooks/\d+/[\w-]+/?$")
_CATEGORIA = {"usuario": "usuarios", "canal": "canales"}


def _permiso(nombre: str):
    if getattr(config, "PERMISOS", {}).get(nombre, True):
        return None
    return f"El permiso '{nombre}' está desactivado en la configuración (PERMISOS)."


# ------------------------------ discord.json ------------------------------
def archivo() -> Path:
    return Path(getattr(config, "DISCORD_FILE", _AQUI / "discord.json"))


def asegurar_archivo():
    f = archivo()
    if not f.exists() and EJEMPLO.exists():
        try:
            shutil.copyfile(EJEMPLO, f)
        except Exception:
            pass


def cargar() -> dict:
    """{"usuarios": {...}, "canales": {...}}. Lanza ValueError con un mensaje claro si el JSON está mal."""
    asegurar_archivo()
    f = archivo()
    vacio = {"usuarios": {}, "canales": {}, "salas": {}}  # «servidores» se aplana en canales y salas
    if not f.exists():
        return vacio
    try:
        crudo = json.loads(f.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ValueError(f"discord.json tiene un error de formato (línea {e.lineno}, columna {e.colno}): {e.msg}. "
                         "Revisa comas y comillas.") from None
    if not isinstance(crudo, dict):
        raise ValueError("discord.json debe ser un objeto con «usuarios» y «canales».")
    res = {}
    for cat in vacio:
        sec = crudo.get(cat, {})
        if not isinstance(sec, dict):
            raise ValueError(f"En discord.json «{cat}» debe ser un objeto con un elemento por nombre.")
        res[cat] = {k: v for k, v in sec.items() if not k.startswith("_") and isinstance(v, dict)}
    srvs = crudo.get("servidores", {})
    if not isinstance(srvs, dict):
        raise ValueError("En discord.json «servidores» debe ser un objeto con un servidor por nombre.")
    for sn, sd in srvs.items():
        if sn.startswith("_") or not isinstance(sd, dict):
            continue
        for cat in ("canales", "salas"):
            sub = sd.get(cat, {})
            if not isinstance(sub, dict):
                raise ValueError(f"En discord.json, «{cat}» del servidor «{sn}» debe ser un objeto.")
            for n, d in sub.items():
                if n.startswith("_") or not isinstance(d, dict):
                    continue
                e = dict(d)
                e["servidor"] = sn
                e["_nombre"] = str(d.get("nombre") or n)
                e["_srv_alias"] = _alias(sd)
                e["alias"] = _alias(d) + [n]   # el nombre suelto también la encuentra
                if sd.get("ejemplo"):
                    e["ejemplo"] = True
                res[cat][f"{n} ({sn})"] = e
    return res


def _real(nombre: str, d: dict) -> str:
    """Nombre REAL en Discord: el campo «nombre» si existe; si no, el de la clave. El alias dicho por el usuario nunca se busca."""
    return str(d.get("nombre") or d.get("_nombre") or nombre).strip()


def _servidores_conocidos() -> dict:
    """{nombre_servidor: [alias]} a partir de discord.json."""
    res = {}
    try:
        datos = cargar()
        for cat in ("canales", "salas"):
            for d in datos[cat].values():
                if d.get("servidor"):
                    res.setdefault(str(d["servidor"]), []).extend(d.get("_srv_alias", []))
    except ValueError:
        pass
    return res


def _resolver_servidor(servidor: str):
    """(nombre_canónico, mensaje_error). Acepta alias y escrituras parecidas (el reconocimiento de voz falla: «pppoe causas» ≈ «tp causas»)."""
    conocidos = _servidores_conocidos()
    if not servidor.strip() or not conocidos:
        return servidor.strip(), None
    q = _n(servidor)
    for nombre, alias in conocidos.items():
        if q in {_n(x) for x in [nombre] + alias}:
            return nombre, None
    puntaje = []
    for nombre, alias in conocidos.items():
        mejor = max(difflib.SequenceMatcher(None, q, _n(x)).ratio() for x in [nombre] + alias)
        puntaje.append((mejor, nombre))
    puntaje.sort(reverse=True)
    if puntaje[0][0] >= 0.6 and (len(puntaje) == 1 or puntaje[0][0] - puntaje[1][0] >= 0.1):
        return puntaje[0][1], None
    return None, f"No tengo el servidor «{servidor}» en discord.json. Tengo: {', '.join(conocidos)}."


def _del_servidor(d: dict, servidor: str) -> bool:
    """¿Esta entrada es del servidor indicado (por su nombre o alias)? Sin servidor indicado, siempre sí."""
    if not servidor.strip():
        return True
    q = _n(servidor)
    return q in {_n(x) for x in [str(d.get("servidor", ""))] + list(d.get("_srv_alias", []))}


def _alias(d: dict) -> list:
    a = d.get("alias", [])
    return [a] if isinstance(a, str) else [x for x in a if isinstance(x, str)]


def _nombres_norm(nombre: str, d: dict) -> set:
    """Nombre, alias y también el usuario exacto de Discord (decir «niko» sirve si su usuario es niko)."""
    extra = [d["usuario"]] if isinstance(d.get("usuario"), str) else []
    return {_n(x) for x in [nombre] + _alias(d) + extra if _n(x)}


def _buscar(nombre: str, tipo: str = "") -> list:
    """[(categoria, nombre, datos)]. Nombre o alias completo; sin adivinar. Con '#' o '@' al inicio fija el tipo."""
    q = _n(nombre.lstrip("@#"))
    if not q:
        return []
    datos = cargar()
    cats = [_CATEGORIA[tipo]] if tipo in _CATEGORIA else ["usuarios", "canales"]
    if nombre[:1] == "#":
        cats = ["canales"]
    elif nombre[:1] == "@":
        cats = ["usuarios"]
    exactos = [(c, n, d) for c in cats for n, d in datos[c].items() if q in _nombres_norm(n, d)]
    if exactos:
        return exactos
    qt = set(q.split())
    return [(c, n, d) for c in cats for n, d in datos[c].items() if any(qt <= set(x.split()) for x in _nombres_norm(n, d))]


# ------------------------------ Envío ------------------------------
def _webhooks() -> dict:
    """Compatibilidad: nombre normalizado -> url, desde variables DISCORD_WEBHOOK_<NOMBRE> del .env."""
    res = {}
    for k, v in os.environ.items():
        if k.upper().startswith("DISCORD_WEBHOOK_") and v.strip():
            res[_n(k[len("DISCORD_WEBHOOK_"):].replace("_", " "))] = v.strip()
    return res


def _por_webhook(url: str, mensaje: str, nombre: str) -> str:
    if not _HOOK.match(url):
        return f"El webhook de «{nombre}» no tiene un formato válido de Discord."
    try:
        r = requests.post(url, json={"content": mensaje, "allowed_mentions": {"parse": []}}, timeout=20)
    except requests.RequestException as e:
        return f"No pude conectar con Discord: {e}"
    if r.status_code in (200, 204):
        return f"Mensaje enviado a #{nombre} en Discord."
    if r.status_code == 429:
        return "Discord me pidió esperar un momento (límite de mensajes). Inténtalo de nuevo en unos segundos."
    if r.status_code in (401, 404):
        return f"El webhook de «{nombre}» ya no existe o es inválido; crea uno nuevo y actualízalo en discord.json."
    return f"Discord respondió con error {r.status_code}: {r.text[:150]}"


def _discord_al_frente(segundos: float = 15) -> bool:
    import tools_pc
    fin = time.time() + segundos
    while time.time() < fin:
        t, exe = tools_pc._ventana()
        if "discord" in t.lower() or "discord" in exe:
            return True
        time.sleep(0.5)
    return False


def _esp(seg: float):
    """Pausa escalada por DISCORD_ESPERA (config_local.py): súbela (p. ej. 1.5) si tu PC o internet son lentos."""
    time.sleep(seg * float(getattr(config, "DISCORD_ESPERA", 1.0)))


def _por_escritorio(destino: str, mensaje: str, tipo: str, servidor: str = "", tambien: str = "", verificar: bool = True) -> str:
    import tools, tools_pc
    if (m := _permiso("control_pc")):
        return m
    prefijo = "" if destino[:1] in "@#!*" else {"usuario": "@", "canal": "#"}.get(tipo, "")
    limpio = destino.lstrip("@#!*").strip()
    try:
        tools.abrir_app("discord")
        if not _discord_al_frente():
            return "No pude abrir Discord Desktop o no se puso al frente. ¿Está instalado y con la sesión iniciada?"
        time.sleep(2.0)
        pg = tools_pc._pg()
        pg.hotkey("ctrl", "k"); _esp(0.9)                  # buscador rápido de Discord
        tools_pc._pegar(prefijo + limpio); _esp(2.6)       # esperar a que termine «Buscando a todos los usuarios»
        pg.press("enter"); _esp(2.0)
        if verificar and getattr(config, "DISCORD_VERIFICAR_TITULO", True):
            titulo, exe = tools_pc._ventana()
            if "discord" not in titulo.lower() and "discord" not in exe:
                return "Discord dejó de estar al frente; no envié nada."
            tn = _n(titulo)
            otros = [tambien] if isinstance(tambien, str) else list(tambien or [])
            if _n(limpio) not in tn and not any(_n(x) and _n(x) in tn for x in otros):
                return (f"No pude confirmar que se abrió el chat de «{limpio}» (la ventana dice «{titulo}»), así que no envié nada para "
                        "no mandarlo a la persona o canal equivocado. Revisa el nombre exacto en discord.json.")
            if servidor and _n(servidor) not in _n(titulo):
                return (f"No pude confirmar que sea el servidor «{servidor}» (la ventana dice «{titulo}»), así que no envié nada. "
                        "Si tu Discord no muestra el servidor en la ventana, borra el campo «servidor» de ese canal en discord.json.")
        tools_pc._pegar(mensaje); _esp(0.5)
        pg.press("enter")
        return f"Mensaje enviado a {prefijo}{limpio} en Discord."
    except Exception as e:
        return f"No pude enviar el mensaje por Discord: {e}"


def enviar_discord(destino: str, mensaje: str, tipo: str = "", servidor: str = "") -> str:
    """Envía un mensaje a Discord AHORA MISMO (sin pedir confirmación). destino = usuario o canal de discord.json."""
    if (m := _permiso("discord")):
        return m
    destino, mensaje = destino.strip(), mensaje.strip()
    if not destino or len(destino) > 80 or not mensaje:
        return "Necesito un destino (canal o persona) y el mensaje."
    if len(mensaje) > 2000:
        return "Discord solo permite mensajes de hasta 2000 caracteres; acórtalo."
    try:
        if servidor.strip():
            servidor, err = _resolver_servidor(servidor)
            if err:
                return err
        cands = _buscar(destino, tipo)
        if servidor.strip():
            cands = [c for c in cands if c[0] == "canales" and _del_servidor(c[2], servidor)]
    except ValueError as e:
        return str(e)
    if len(cands) > 1:
        lista = ", ".join(f"{n} ({'canal' if c == 'canales' else 'usuario'})" for c, n, _d in cands[:6])
        return f"Hay varios destinos en discord.json que coinciden con «{destino}»: {lista}. Dime cuál (usuario o canal)."
    if not cands and servidor.strip():
        return f"No encontré «{destino}» en el servidor «{servidor}» de discord.json."
    if cands:
        cat, nombre, d = cands[0]
        if d.get("ejemplo"):
            return (f"«{nombre}» en discord.json todavía es de ejemplo. Pon los datos reales y borra la línea \"ejemplo\": true.")
        if cat == "canales":
            hook = str(d.get("webhook", "") or "").strip()
            real = _real(nombre, d)
            if hook:
                return _por_webhook(hook, mensaje, real)
            return _por_escritorio(real, mensaje, "canal", str(d.get("servidor", "") or "").strip())
        return _por_escritorio(str(d.get("usuario", "") or "").strip() or nombre, mensaje, "usuario",
                                 tambien=[d.get("nombre"), d.get("nombre_visible")],
                                 verificar=bool(d.get("nombre") or d.get("nombre_visible") or not d.get("usuario")))
    # No está en discord.json: webhook del .env (compatibilidad) o búsqueda directa en Discord Desktop
    hooks = _webhooks()
    clave = _n(destino.lstrip("#"))
    if clave in hooks and tipo != "usuario":
        return _por_webhook(hooks[clave], mensaje, destino.lstrip("#"))
    return _por_escritorio(destino, mensaje, tipo)


# ------------------------------ Llamadas (canales de voz) ------------------------------
def unirse_llamada_discord(sala: str, servidor: str = "") -> str:
    """Entra a un canal de voz de Discord por su nombre, usando Discord Desktop (Ctrl+K con «!»)."""
    if (m := _permiso("discord")) or (m := _permiso("control_pc")):
        return m
    import tools, tools_pc
    sala = sala.strip().lstrip("!#🔊 ").strip()
    if not sala or len(sala) > 80:
        return "Dime el nombre de la sala de voz."
    if servidor.strip():
        servidor, err = _resolver_servidor(servidor)
        if err:
            return err
    try:
        cands = [(n, d) for n, d in cargar()["salas"].items()
                 if _n(sala) in _nombres_norm(n, d) and _del_servidor(d, servidor)]
    except ValueError as e:
        return str(e)
    if len(cands) > 1:
        return f"Hay varias salas en discord.json que coinciden con «{sala}»: {', '.join(n for n, _ in cands[:6])}. Dime cuál."
    if cands:
        nombre, d = cands[0]
        if d.get("ejemplo"):
            return f"«{nombre}» en discord.json todavía es de ejemplo. Pon los datos reales y borra la línea \"ejemplo\": true."
        sala, servidor = _real(nombre, d), str(d.get("servidor", "") or "").strip() or servidor.strip()
    try:
        tools.abrir_app("discord")
        if not _discord_al_frente():
            return "No pude abrir Discord Desktop o no se puso al frente. ¿Está instalado y con la sesión iniciada?"
        time.sleep(2.0)
        pg = tools_pc._pg()
        pg.hotkey("ctrl", "k"); time.sleep(0.7)
        tools_pc._pegar("!" + sala); time.sleep(1.4)      # «!» busca solo canales de voz
        pg.press("enter"); time.sleep(2.0)
        titulo, exe = tools_pc._ventana()
        if "discord" not in titulo.lower() and "discord" not in exe:
            return "Discord dejó de estar al frente; no pude confirmar la llamada."
        tn = _n(titulo)
        if getattr(config, "DISCORD_VERIFICAR_TITULO", True):
            if _n(sala) not in tn:
                return (f"No pude confirmar que se abrió la sala «{sala}» (la ventana dice «{titulo}»). Revisa que el nombre sea exacto "
                        "y mira en Discord si entró.")
            if servidor and _n(servidor) not in tn:
                return (f"Abrí una sala llamada «{sala}», pero no veo el servidor «{servidor}» en la ventana («{titulo}»). "
                        "Puede ser de otro servidor; revísalo en Discord.")
        return f"Entré a la sala de voz «{sala}» en Discord."
    except Exception as e:
        return f"No pude entrar a la llamada de Discord: {e}"


# ------------------------------ Consultar y guardar ------------------------------
def buscar_discord(nombre: str = "", servidor: str = "") -> str:
    """Sin nombre: lista lo guardado. Con nombre: dice a qué entrada de discord.json corresponde y QUÉ nombre real se buscará en
    Discord (los webhooks nunca se muestran). Sirve para comprobar alias."""
    try:
        d = cargar()
        if not nombre.strip():
            if not d["usuarios"] and not d["canales"] and not d["salas"]:
                return f"No hay destinos de Discord guardados todavía (archivo: {archivo()})."
            return (f"Usuarios: {', '.join(d['usuarios']) or '—'}. Canales: {', '.join(d['canales']) or '—'}. "
                    f"Salas de voz: {', '.join(d['salas']) or '—'}. (archivo: {archivo()})")
        if servidor.strip():
            servidor, err = _resolver_servidor(servidor)
            if err:
                return err
        q = _n(nombre.lstrip("@#!"))
        cands = [(c, n, x) for c, n, x in _buscar(nombre) if _del_servidor(x, servidor)]
        cands += [("salas", n, x) for n, x in d["salas"].items()
                  if q in _nombres_norm(n, x) and _del_servidor(x, servidor)]
    except ValueError as e:
        return str(e)
    if not cands:
        return (f"No tengo «{nombre}» en discord.json (archivo: {archivo()}), pero enviar_discord lo busca igual directamente en Discord: "
                "no hace falta guardarlo ni avisar al usuario; llama a enviar_discord.")
    if len(cands) > 1:
        tipos = {"canales": "canal", "usuarios": "usuario", "salas": "sala de voz"}
        return "Varios coinciden: " + ", ".join(f"{n} ({tipos[c]})" for c, n, _d in cands[:6]) + ". Aclara cuál."
    cat, n, x = cands[0]
    ej = " (de ejemplo: no se usa hasta que borres \"ejemplo\": true)" if x.get("ejemplo") else ""
    srv = f" del servidor «{x['servidor']}»" if x.get("servidor") else ""
    if cat == "usuarios":
        return f"«{nombre}» = {n}: en Discord se busca el usuario «@{x.get('usuario', n)}»{ej}."
    real = _real(n, x)
    if cat == "salas":
        return f"«{nombre}» = sala de voz{srv}: en Discord se busca «{real}»{ej}."
    hook = "con webhook (sin abrir Discord)" if str(x.get("webhook", "") or "").strip() else "sin webhook (por Discord Desktop)"
    return f"«{nombre}» = canal{srv}: en Discord se busca «#{real}», {hook}{ej}."


if __name__ == "__main__":   # prueba rápida:  python tools_discord.py bolso   /   python tools_discord.py "sala uno" "tp causas"
    import sys
    print(buscar_discord(*(sys.argv[1:3])))


def guardar_discord(nombre: str, tipo: str = "usuario", usuario: str = "", servidor: str = "", alias: str = "") -> str:
    """Crea o actualiza un usuario o canal en discord.json. Los datos deben venir de lo que escribió el usuario.
    Los webhooks son secretos: se pegan a mano en discord.json, no los guarda Jarvis."""
    import tools_google
    nombre, tipo = nombre.strip(), (tipo or "usuario").strip().lower()
    if tipo not in _CATEGORIA:
        return "El tipo debe ser «usuario» o «canal»."
    if not nombre or len(nombre) > 60 or nombre.startswith("_"):
        return "Dime el nombre."
    if tipo == "usuario" and not usuario.strip():
        return "Dime el usuario exacto de Discord de esa persona."
    ctx = tools_google._contexto["texto"]
    nuevos = {}
    if usuario.strip():
        if usuario.strip().lower() not in ctx:
            return "No veo ese usuario de Discord en lo que me dijiste; por seguridad no lo guardo. Dímelo escrito."
        nuevos["usuario"] = usuario.strip()
    if servidor.strip():
        if servidor.strip().lower() not in ctx:
            return "No veo ese servidor en lo que me dijiste; por seguridad no lo guardo. Dímelo escrito."
        nuevos["servidor"] = servidor.strip()
    cat = _CATEGORIA[tipo]
    try:
        f = archivo()
        asegurar_archivo()
        crudo = json.loads(f.read_text(encoding="utf-8-sig")) if f.exists() else {}
        existentes = [(c, n, d) for c, n, d in _buscar(nombre, tipo) if c == cat]
        if len(existentes) > 1:
            return f"Varios coinciden con «{nombre}»: {', '.join(n for _c, n, _d in existentes[:6])}. Dime el nombre completo."
        clave = existentes[0][1] if existentes else nombre
        seccion = crudo.setdefault(cat, {})
        entrada = seccion.get(clave, {}) if isinstance(seccion.get(clave), dict) else {}
        entrada.update(nuevos)
        entrada.pop("ejemplo", None)
        if alias.strip():
            lista = entrada.get("alias", [])
            lista = [lista] if isinstance(lista, str) else list(lista)
            entrada["alias"] = lista + [a.strip() for a in alias.split(",") if a.strip() and a.strip() not in lista]
        seccion[clave] = entrada
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(crudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, f)
    except json.JSONDecodeError as e:
        return f"discord.json tiene un error de formato (línea {e.lineno}); arréglalo antes de guardar."
    except Exception as e:
        return f"No pude guardar en discord.json: {e}"
    extra = " Para enviar sin abrir Discord, pega un webhook de ese canal en discord.json." if tipo == "canal" else ""
    return f"{'Actualicé' if existentes else 'Guardé'} {tipo} «{clave}» en discord.json.{extra}"


# ------------------------------ Registro para el LLM ------------------------------
def _t(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


S = {"type": "string"}
_TIPO = {"type": "string", "enum": ["usuario", "canal"]}
SPEC = [
    _t("enviar_discord", "Envía un mensaje a Discord de inmediato, sin pedir confirmación. destino = nombre (o alias) de un usuario o canal "
                         "de discord.json, tal como lo dijo el usuario; tipo = usuario o canal solo si el usuario lo aclara; servidor solo si el usuario dice en qué servidor",
       {"destino": S, "mensaje": S, "tipo": _TIPO, "servidor": S}, ["destino", "mensaje"]),
    _t("unirse_llamada_discord", "Entra a una llamada (canal de voz) de Discord por el nombre de la sala. servidor solo si el usuario lo dice",
       {"sala": S, "servidor": S}, ["sala"]),
    _t("buscar_discord", "Lista lo guardado de Discord, o dice qué nombre real se buscará para un alias. No hace falta para enviar", {"nombre": S, "servidor": S}, []),
    _t("guardar_discord", "Guarda o actualiza un usuario (con su usuario exacto de Discord) o un canal (con servidor opcional) en discord.json. "
                          "Solo con datos que el usuario escribió en su mensaje",
       {"nombre": S, "tipo": _TIPO, "usuario": S, "servidor": S, "alias": S}, ["nombre"]),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in SPEC}

try:
    asegurar_archivo()
except Exception:
    pass
