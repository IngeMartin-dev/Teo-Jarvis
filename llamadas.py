"""Llamadas de WhatsApp: Jarvis las contesta cuando se lo dices, o solo si no respondes a tiempo.

Flujo:
  1. Entra una llamada (Jarvis la detecta solo, o le dices «Jarvis, me están llamando por WhatsApp»).
  2. Jarvis te avisa por voz y empieza a contar LLAMADA_ESPERA_SEG segundos (15 por defecto).
  3. Si dices «contesta» -> la acepta. «Rechaza» -> la rechaza. «Yo contesto» / «yo me encargo» -> la dejas en tus manos.
  4. Si pasa el tiempo sin que digas nada, Jarvis la contesta, dice el saludo (LLAMADA_SALUDO), te manda un aviso al celular,
     se queda LLAMADA_PERMANENCIA_SEG segundos en la línea y se despide y cuelga.
Las videollamadas nunca se contestan solas (para no encender tu cámara): solo te avisa al celular.

La lógica está separada de Windows (ui_llamadas.py) para poder probarla sin WhatsApp.
"""
import re, threading, time
import config, notificaciones

# ---------------- Frases ----------------
_WHATSAPP = r"(whats\s?app|wats\s?app|guats\s?app|wasap|guasap)"
_RE_WHATSAPP = re.compile(_WHATSAPP, re.I)
_RE_LLAMADA = re.compile(r"\bllam(ada|adas|an|ando|o|as)\b", re.I)
_RE_ANUNCIO = re.compile(
    r"\b(me\s+est[aá]n?\s+llamando|me\s+llama(n)?\b|tengo\s+una\s+llamada|llamada\s+entrante|est[aá]n?\s+llamando|"
    r"entra\s+una\s+llamada|me\s+entra\s+una\s+llamada)", re.I)
_RE_YO = re.compile(r"\b(yo\s+(la\s+)?(contesto|respondo|atiendo|tomo|me\s+encargo|hablo)|d[eé]jame\s+a\s+m[ií]|"
                    r"d[eé]jala|ya\s+(la\s+)?(contesto|tomo)|la\s+tomo\s+yo)\b", re.I)
_RE_RECHAZAR = re.compile(r"\b(rechaza(la|r)?|rech[aá]zala|no\s+(la\s+)?contestes|no\s+(la\s+)?respondas|"
                          r"no\s+(la\s+)?atiendas|cuelga(la)?|colgar|ignora(la|r)?)\b", re.I)
_RE_ACEPTAR = re.compile(r"\b(contesta(la|r)?|cont[eé]stala|responde(la)?|resp[oó]ndela|acepta(la|r)?|ac[eé]ptala|"
                         r"atiende(la)?|at[ié]ndela|descuelga|toma\s+la\s+llamada)\b", re.I)
_RE_DIAGNOSTICO = re.compile(r"\bdiagn[oó]stic\w*\b.*\bllamada\b|\bllamada\b.*\bdiagn[oó]stic\w*\b", re.I)
_COLCHON_VOZ = 3.0   # segundos extra cuando el usuario avisa de la llamada (lo que tarda Jarvis en responder en voz alta)
_PERDIDAS_MAX = 3    # lecturas seguidas sin ver la ventana antes de dar la llamada por terminada


def _cfg(nombre, defecto):
    return getattr(config, nombre, defecto)


def _permitido() -> bool:
    return bool(_cfg("PERMISOS", {}).get("llamadas", True))


class Gestor:
    """Máquina de estados de las llamadas. Estados:
    libre | esperando (suena; cuenta atrás) | jarvis (la contestó Jarvis) | usuario (la contestaste tú) | ignorando."""

    def __init__(self, ui=None, hablar=None, hablar_llamada=None, avisar=None, escribir=None,
                 reloj=time.time, dormir=time.sleep, en_llamada=None):
        self._ui = ui
        self._hablar = hablar or (lambda t: None)
        self._hablar_llamada = hablar_llamada or (lambda t: None)
        self._avisar = avisar or notificaciones.avisar_celular
        self._escribir = escribir or (lambda quien, texto: None)
        self.reloj, self.dormir = reloj, dormir
        self._en_llamada = en_llamada or (lambda activo: None)   # avisa a voice.py para que Jarvis calle durante la llamada
        self._lock = threading.RLock()
        self.estado = "libre"
        self.info = None
        self.origen = ""
        self.deadline = None
        self.hasta = None
        self._hablando = False
        self._colgar_pedido = False
        self._perdidas = 0

    # ---------- acceso a la interfaz de Windows (perezoso: así se puede probar sin Windows) ----------
    @property
    def ui(self):
        if self._ui is None:
            import ui_llamadas
            self._ui = ui_llamadas
        return self._ui

    def _buscar(self):
        try:
            return self.ui.buscar_llamada()
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if msg != getattr(self, "_ultimo_error", None):   # avisa de cada error distinto una sola vez
                self._ultimo_error = msg
                self._escribir("Jarvis", f"No puedo leer las ventanas de WhatsApp: {msg}")
            return None

    # ---------- utilidades ----------
    def _fijar(self, estado: str):
        self.estado = estado
        self._en_llamada(estado in ("jarvis", "usuario"))

    def _reset(self):
        self.info, self.origen, self.deadline, self.hasta = None, "", None, None
        self._hablando, self._colgar_pedido, self._perdidas = False, False, 0
        self._fijar("libre")

    def _usuario(self) -> str:
        return _cfg("USUARIO_NOMBRE", "mi usuario")

    def _quien(self, info) -> str:
        n = (info or {}).get("nombre") or ""
        return n if n else "alguien"

    def _notificar(self, info, texto: str):
        ok, msg = self._avisar(texto, "Llamada de WhatsApp", True)
        if not ok:
            self._escribir("Jarvis", msg)

    # ---------- ciclo principal ----------
    def tick(self):
        """Una lectura de la pantalla y los cambios de estado que correspondan."""
        if not _permitido() or not _cfg("LLAMADAS_VIGILAR", True):
            return
        info = self._buscar()
        ahora = self.reloj()
        with self._lock:
            est = self.estado
            self._perdidas = 0 if info else self._perdidas + 1
            if est == "libre":
                if info and info["tipo"] == "entrante":
                    self._empezar_espera(info, "auto", ahora)
            elif est == "esperando":
                if info and info["tipo"] == "entrante" and self.info is None:
                    self.info = info                            # avisaste tú y la ventana apareció después
                if info and info["tipo"] == "activa":          # la contestaste tú a mano
                    self.deadline = None
                    self._fijar("usuario")
                elif self.info is not None and self._perdidas >= _PERDIDAS_MAX:   # colgaron antes de tiempo
                    self._reset()
                elif self.deadline is not None and ahora >= self.deadline:
                    self._autocontestar(info or self.info)
            elif est == "jarvis":
                if self._perdidas >= _PERDIDAS_MAX and not self._hablando:   # colgó quien llamaba
                    self._reset()
                elif self.hasta is not None and ahora >= self.hasta and not self._hablando:
                    self._despedir_y_colgar()
            elif est in ("usuario", "ignorando"):
                if self._perdidas >= _PERDIDAS_MAX:
                    self._reset()

    def ejecutar(self):
        """Bucle del hilo vigilante."""
        try:  # pywinauto usa COM; este hilo necesita inicializarlo
            import comtypes
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except Exception:
            pass
        while True:
            try:
                self.tick()
            except Exception as e:
                self._escribir("Jarvis", f"Error vigilando llamadas: {e}")
                self.dormir(5)
            self.dormir(_cfg("LLAMADAS_INTERVALO", 1.0))

    # ---------- empezar la espera ----------
    def _empezar_espera(self, info, origen: str, ahora: float):
        self.info, self.origen, self._perdidas = info, origen, 0
        self.hasta = None
        self._fijar("esperando")
        if origen == "auto" and _cfg("LLAMADA_ESPERA_SEG", 15) <= 0:
            self.deadline = ahora   # espera 0: contesta de inmediato, sin avisarte por voz ni esperar tu respuesta
        elif origen == "auto":
            self.deadline = None   # la cuenta empieza cuando Jarvis termina de avisarte
            threading.Thread(target=self._anunciar, args=(info,), daemon=True).start()
        else:
            self.deadline = ahora + _cfg("LLAMADA_ESPERA_SEG", 15) + _COLCHON_VOZ

    def _anunciar(self, info):
        quien = (info or {}).get("nombre")
        texto = (f"Te está llamando {quien} por WhatsApp. Di contesta y la acepto." if quien
                 else "Te están llamando por WhatsApp. Di contesta y la acepto.")
        self._escribir("Jarvis", texto)
        try:
            self._hablar(texto)
        finally:
            with self._lock:
                if self.estado == "esperando" and self.deadline is None:
                    self.deadline = self.reloj() + _cfg("LLAMADA_ESPERA_SEG", 15)

    # ---------- Jarvis contesta por ti ----------
    def _autocontestar(self, info):
        """Se acabó el tiempo sin que dijeras nada. Se llama con el lock tomado."""
        self.deadline = None
        if not _cfg("LLAMADAS_AUTO_CONTESTAR", True):
            self._fijar("ignorando")
            self._en_hilo(self._notificar, info, f"{self._quien(info)} te está llamando por WhatsApp.")
            return
        if info and info.get("video"):
            self._fijar("ignorando")
            self._en_hilo(self._notificar, info, f"{self._quien(info)} te está haciendo una videollamada por WhatsApp. "
                          "No la contesté para no encender tu cámara.")
            self._escribir("Jarvis", "Es una videollamada: no la contesto sola. Te avisé al celular.")
            return
        self._hablando = True
        self._fijar("jarvis")
        threading.Thread(target=self._atender, args=(info,), daemon=True).start()

    def _en_hilo(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def _atender(self, info):
        ok = False
        try:
            ok = self.ui.aceptar()
        except Exception:
            ok = False
        if not ok:
            with self._lock:
                self._hablando = False
                self._fijar("ignorando")
            self._escribir("Jarvis", "No logré contestar la llamada de WhatsApp.")
            if (info or {}).get("tipo") == "entrante":   # solo avisa si de verdad había una llamada visible
                self._notificar(info, f"{self._quien(info)} te está llamando por WhatsApp y no pude contestar.")
            return
        self._escribir("Jarvis", f"Contesté la llamada de {self._quien(info)}.")
        self._notificar(info, f"{self._quien(info)} te está llamando por WhatsApp. "
                        "Jarvis contestó y dijo que esperen o dejen un mensaje.")
        self.dormir(1.2)   # deja que se establezca el audio antes de hablar
        try:
            self._hablar_llamada(_cfg("LLAMADA_SALUDO", "Hola, soy Jarvis.").format(usuario=self._usuario()))
        finally:
            with self._lock:
                self._hablando = False
                if self.estado == "jarvis":
                    self.hasta = self.reloj() + (0 if self._colgar_pedido else _cfg("LLAMADA_PERMANENCIA_SEG", 45))

    def _despedir_y_colgar(self):
        """Se llama con el lock tomado."""
        self._hablando = True
        self.hasta = None
        self._en_hilo(self._colgar)

    def _colgar(self):
        try:
            self._hablar_llamada(_cfg("LLAMADA_DESPEDIDA", "Hasta luego.").format(usuario=self._usuario()))
        finally:
            ok = False
            try:
                ok = self.ui.colgar()
            except Exception:
                pass
            if not ok:
                self._escribir("Jarvis", "No pude colgar la llamada; cuélgala tú.")
            with self._lock:
                if self.estado == "jarvis":
                    self._reset()

    # ---------- órdenes del usuario ----------
    def anunciar_usuario(self) -> str:
        info = self._buscar()   # fuera del lock: leer la pantalla puede tardar un par de segundos
        with self._lock:
            if self.estado == "esperando":
                return "Ya estoy atento a esa llamada. Di «contesta» y la acepto."
            if self.estado in ("jarvis", "usuario") or (info and info["tipo"] == "activa"):
                return "Ya hay una llamada en curso."
            self._empezar_espera(info, "usuario", self.reloj())
        return (f"Entendido. Dime «contesta» y la acepto; si no dices nada en {_cfg('LLAMADA_ESPERA_SEG', 15)} "
                "segundos, la contesto yo.")

    def aceptar_usuario(self) -> str:
        with self._lock:
            self.deadline = None
            ok = False
            try:
                ok = self.ui.aceptar()
            except Exception:
                pass
            if not ok:
                if self.estado == "esperando":
                    self._reset()
                return ("No veo ninguna llamada entrante de WhatsApp que pueda contestar. "
                        "Si está sonando, di «diagnostica la llamada».")
            self.hasta, self._perdidas = None, 0
            self._fijar("usuario")
        return "Listo, la contesté."

    def rechazar_usuario(self) -> str:
        with self._lock:
            est = self.estado
            self.deadline = None
            if est == "jarvis":                       # «cuelga» mientras Jarvis atiende: se despide y cuelga
                if self._hablando:
                    self._colgar_pedido = True
                else:
                    self.hasta = self.reloj()
                return "Voy a colgar la llamada."
            ok = False
            try:
                ok = self.ui.colgar() if est == "usuario" else self.ui.rechazar()
            except Exception:
                pass
            if est in ("esperando", "usuario"):
                self._reset()
            if est == "usuario":
                return "Llamada colgada." if ok else "No pude colgar la llamada; cuélgala tú."
        return "Llamada rechazada." if ok else "No veo ninguna llamada que pueda rechazar."

    def lo_tomo_yo(self) -> str:
        with self._lock:
            if self.estado in ("esperando", "jarvis"):
                self.deadline, self.hasta = None, None
                self._fijar("usuario")
                return "Va, es toda tuya. No la contesto."
        return "No hay ninguna llamada pendiente."

    def diagnosticar(self, segundos: int = 40) -> str:
        """Observa la pantalla `segundos` segundos y reporta qué ventanas aparecen (para llamarte mientras tanto)."""
        if getattr(self, "_observando", False):
            return "Ya estoy observando. Llámame por WhatsApp desde otro teléfono."
        self._observando = True
        threading.Thread(target=self._observar, args=(segundos,), daemon=True).start()
        return (f"Voy a observar {segundos} segundos. Llámame ahora por WhatsApp desde otro teléfono "
                "y deja sonar la llamada. Te dejo el resultado en el chat.")

    def _observar(self, segundos: int):
        try:
            try:
                base = list(self.ui.instantanea())
            except Exception as e:
                base = [f"No pude leer la pantalla: {type(e).__name__}: {e}"]
            vistas, nuevas = set(base), []
            fin = self.reloj() + segundos
            while self.reloj() < fin:
                self.dormir(2)
                try:
                    actual = list(self.ui.instantanea())
                except Exception:
                    continue
                for l in actual:
                    if l not in vistas:
                        vistas.add(l)
                        nuevas.append(l)
            partes = ["NUEVO durante la observación:"] + (nuevas or ["(nada: no apareció ninguna ventana nueva)"]) + \
                     ["", "Ya estaba antes:"] + base
            informe = "\n".join(partes)
            ruta = None
            try:
                from pathlib import Path
                ruta = Path.home() / ".jarvis" / "diagnostico_llamada.txt"
                ruta.write_text(informe, encoding="utf-8")
            except Exception:
                ruta = None
            self._escribir("Jarvis", "Resultado de la observación (revisa que no haya nada privado antes de compartirlo):\n"
                           + informe[:1800] + (f"\n\nGuardado en {ruta}" if ruta else ""))
        finally:
            self._observando = False

    # ---------- texto y voz ----------
    def _sin_wake(self, texto: str) -> str:
        t = texto.lower().strip()
        try:
            m = re.compile(_cfg("WAKE_REGEX", r"^$"), re.I).match(t)
            if m:
                t = t[m.end():]
        except re.error:
            pass
        return t.strip(" ,.!¡¿?")

    def manejar_texto(self, texto: str):
        """Respuesta (str) si el texto trata de una llamada de WhatsApp; None si no tiene que ver con llamadas."""
        if not _permitido():
            return None
        t = self._sin_wake(texto)
        est = self.estado
        habla_llamada = bool(_RE_LLAMADA.search(t))
        if _RE_DIAGNOSTICO.search(t):
            return self.diagnosticar()
        if est in ("esperando", "jarvis", "usuario") or habla_llamada:
            if _RE_YO.search(t):
                return self.lo_tomo_yo()
            if _RE_RECHAZAR.search(t) and (est != "libre" or habla_llamada):
                return self.rechazar_usuario()
            if _RE_ACEPTAR.search(t) and (est != "libre" or habla_llamada):
                if est in ("jarvis", "usuario"):
                    return "Ya hay una llamada en curso."
                return self.aceptar_usuario()
        if _RE_ANUNCIO.search(t) and _RE_WHATSAPP.search(t):
            return self.anunciar_usuario()
        return None

    def atajo_voz(self, texto: str) -> bool:
        """Lo llama voice.py con cada frase oída. True = ya se atendió (o se ignoró) y no hay que procesarla más."""
        if not _permitido():
            return False
        t = texto.lower().strip()
        try:
            con_wake = bool(re.compile(_cfg("WAKE_REGEX", r"^$"), re.I).match(t))
        except re.error:
            con_wake = False
        # Durante una llamada en curso, lo que se oye es la conversación (la otra persona por los parlantes): no son órdenes.
        if self.estado in ("jarvis", "usuario") and not con_wake:
            return True
        try:
            respuesta = self.manejar_texto(texto)
        except Exception as e:
            respuesta = f"Error con la llamada: {e}"
        if respuesta is None:
            return False
        self._escribir("Tú", texto)
        self._escribir("Jarvis", respuesta)
        if self.estado not in ("jarvis", "usuario"):   # en llamada Jarvis no habla (se oiría en la llamada)
            self._hablar(respuesta)
        return True


# ---------------- Conexión con voz y arranque ----------------
_gestor = None


def _hablar_normal(texto: str):
    import voice
    ya = voice.ocupado.is_set()
    voice.ocupado.set()
    try:
        voice.hablar(texto)
    finally:
        if not ya:
            voice.ocupado.clear()


def _hablar_en_llamada(texto: str):
    import voice
    voice.hablar_en_llamada(texto)


def _marcar_en_llamada(activo: bool):
    import voice
    if activo:
        voice.en_llamada.set()
        voice.conversando.clear()   # no seguir en modo conversación mientras hay una llamada
    else:
        voice.en_llamada.clear()


def obtener(escribir=None) -> Gestor:
    global _gestor
    if _gestor is None:
        _gestor = Gestor(hablar=_hablar_normal, hablar_llamada=_hablar_en_llamada,
                         escribir=escribir, en_llamada=_marcar_en_llamada)
    elif escribir is not None:
        _gestor._escribir = escribir
    return _gestor


def iniciar(escribir=None) -> Gestor:
    """Crea el gestor y arranca el hilo vigilante (si LLAMADAS_VIGILAR). Llamar una vez desde main.py."""
    g = obtener(escribir)
    if _cfg("LLAMADAS_VIGILAR", True) and _permitido():
        threading.Thread(target=g.ejecutar, daemon=True).start()
    return g


def manejar_texto(texto: str):
    """Para brain.py: respuesta si el texto trata de una llamada de WhatsApp; None si no."""
    return obtener().manejar_texto(texto)


# ---------------- Herramientas para el LLM (por si la frase no coincide con las reconocidas arriba) ----------------
def contestar_llamada() -> str:
    return obtener().aceptar_usuario()


def rechazar_llamada() -> str:
    return obtener().rechazar_usuario()


def diagnosticar_llamada() -> str:
    """Muestra qué ventanas y botones de WhatsApp ve Jarvis. Úsalo con una llamada sonando."""
    return obtener().diagnosticar()


def probar_aviso_celular() -> str:
    ok, msg = notificaciones.avisar_celular("Prueba de Jarvis: si lees esto, los avisos al celular funcionan.", "Jarvis")
    return msg


def _t(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


SPEC = [
    _t("contestar_llamada", "Acepta la llamada entrante de WhatsApp que está sonando. Úsalo cuando el usuario pida contestar o aceptar una llamada de WhatsApp.", {}, []),
    _t("rechazar_llamada", "Rechaza la llamada entrante de WhatsApp que está sonando", {}, []),
    _t("diagnosticar_llamada", "Muestra qué ventanas y botones de WhatsApp ve Jarvis (para ajustar la detección de llamadas; úsalo con una llamada sonando)", {}, []),
    _t("probar_aviso_celular", "Envía un aviso de prueba al celular del usuario", {}, []),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in SPEC}
