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
import re, sys, threading, time
import config, notificaciones, registro

# pywinauto/UI Automation works in STA. Set this before its lazy import in
# ui_llamadas.py so pywinauto does not first try MTA and then warn/fallback.
sys.coinit_flags = 2  # COINIT_APARTMENTTHREADED

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
_RE_PRUEBA_VOZ = re.compile(r"\b(prueba|probar|probemos|testea|test)\b.*\bvoz\b.*\b(llamada|cable)\b|"
                            r"\b(prueba|probar)\b.*\b(cable|audio)\b.*\bllamada\b", re.I)
_RE_PRUEBA_OIDO = re.compile(r"\b(prueba|probar|probemos|testea|test)\b.*\b(o[ií]do|escucha|o[ií]r)\b.*\b(llamada)\b", re.I)
_RE_DIAGNOSTICO = re.compile(r"\bdiagn[oó]stic\w*\b.*\bllamada\b|\bllamada\b.*\bdiagn[oó]stic\w*\b", re.I)
_COLCHON_VOZ = 3.0   # segundos extra cuando el usuario avisa de la llamada (lo que tarda Jarvis en responder en voz alta)
_PERDIDAS_MAX = 3    # lecturas seguidas sin ver la ventana antes de dar la llamada por terminada
_ERROR = object()    # la lectura de la pantalla falló o se agotó: no se sabe si hay llamada (NO es «no hay llamada»)
_LIMITE_ESTADO = {"esperando": 120, "aceptando": 120, "jarvis": 900, "ignorando": 300, "usuario": 3600}   # segundos


def _cfg(nombre, defecto):
    return getattr(config, nombre, defecto)


def _permitido() -> bool:
    return bool(_cfg("PERMISOS", {}).get("llamadas", True))


class Gestor:
    """Máquina de estados de las llamadas. Estados:
    libre | esperando (suena; cuenta atrás) | aceptando (Jarvis está pulsando «aceptar»; todavía NO silencia nada) |
    jarvis (la contestó Jarvis) | usuario (la contestaste tú) | ignorando.
    Solo «jarvis» y «usuario» silencian la voz de Jarvis, y solo después de comprobar que la llamada se contestó."""

    def __init__(self, ui=None, hablar=None, hablar_llamada=None, avisar=None, escribir=None,
                 reloj=time.time, dormir=time.sleep, en_llamada=None, conversar=None):
        self._ui = ui
        self._conversar = conversar   # conversar(info, hablar, activo, escribir, avisar) -> dict; None = sin conversación
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
        self._desde = 0.0          # desde cuándo está en el estado actual (para el temporizador de seguridad)
        self._observando = False

    # ---------- acceso a la interfaz de Windows (perezoso: así se puede probar sin Windows) ----------
    @property
    def ui(self):
        if self._ui is None:
            import ui_llamadas
            self._ui = ui_llamadas
        return self._ui

    def _buscar(self):
        """Info de la llamada, None si no hay, o _ERROR si no se pudo leer (no se confunde con «no hay llamada»)."""
        try:
            return self.ui.buscar_llamada()
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            registro.escribir(f"error leyendo WhatsApp: {msg}")
            if msg != getattr(self, "_ultimo_error", None):   # avisa de cada error distinto una sola vez
                self._ultimo_error = msg
                self._escribir("Jarvis", f"No puedo leer las ventanas de WhatsApp: {msg}")
            return _ERROR

    # ---------- utilidades ----------
    def _fijar(self, estado: str):
        anterior = self.estado
        self.estado = estado
        self._desde = self.reloj()
        self._en_llamada(estado in ("jarvis", "usuario"))
        if anterior != estado:
            registro.escribir(f"estado: {anterior} -> {estado}")

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
        fallo = info is _ERROR          # no se pudo leer: ni suma ni resta «llamadas perdidas»
        if fallo:
            info = None
        ahora = self.reloj()
        with self._lock:
            est = self.estado
            # Temporizador de seguridad: ningún estado puede quedarse pegado (y dejar a Jarvis mudo) para siempre.
            limite = _cfg("LLAMADA_MAX_SEG", None) or _LIMITE_ESTADO.get(est)
            if est != "libre" and limite and self._desde and ahora - self._desde > limite:
                registro.escribir(f"temporizador de seguridad: llevaba {ahora - self._desde:.0f}s en «{est}»; reinicio")
                self._escribir("Jarvis", f"Reinicié el estado de llamadas (llevaba demasiado tiempo en «{est}»).")
                self._reset()
                return
            if not fallo:
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
            # est == "aceptando": lo resuelve _atender; el temporizador de arriba es la red de seguridad

    def ejecutar(self):
        """Bucle del hilo vigilante. No toca UI Automation directamente: eso lo hace ui_llamadas en su propio hilo."""
        registro.escribir("vigilante de llamadas iniciado")
        while True:
            try:
                self.tick()
            except Exception as e:
                registro.escribir(f"error en el vigilante: {type(e).__name__}: {e}")
                self._escribir("Jarvis", f"Error vigilando llamadas: {e}")
                self.dormir(5)
            self.dormir(_cfg("LLAMADAS_INTERVALO", 1.0))

    # ---------- empezar la espera ----------
    def _empezar_espera(self, info, origen: str, ahora: float):
        registro.escribir(f"llamada detectada ({origen}): {info}")
        self.info, self.origen, self._perdidas = info, origen, 0
        self.hasta = None
        self._fijar("esperando")
        if origen == "auto" and (_cfg("LLAMADA_ESPERA_SEG", 15) <= 0 or not _cfg("LLAMADA_ANUNCIAR", False)):
            # Sin aviso por voz: la cuenta empieza ya (con espera 0, contesta en la siguiente lectura).
            self.deadline = ahora + max(0, _cfg("LLAMADA_ESPERA_SEG", 15))
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
        self._fijar("aceptando")   # todavía no se silencia nada: primero hay que comprobar que contestó
        threading.Thread(target=self._atender, args=(info,), daemon=True).start()

    def _en_hilo(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def _intentar_aceptar(self) -> bool:
        """Pulsa «aceptar» con UI Automation y, si no se pudo, lo intenta mirando la pantalla (LLAMADA_ACEPTAR_POR_VISION)."""
        ok = False
        try:
            ok = bool(self.ui.aceptar())
        except Exception as e:
            registro.escribir(f"aceptar por UI Automation falló: {type(e).__name__}: {e}")
        registro.escribir(f"aceptar por UI Automation: {ok}")
        if not ok and _cfg("LLAMADA_ACEPTAR_POR_VISION", True):
            ok = self._aceptar_por_vision()
        return ok

    def _aceptar_por_vision(self) -> bool:
        """Segundo intento: mira la pantalla con el modelo de visión, comprueba que sea una llamada de VOZ (nunca de video,
        para no encender la cámara) y hace clic en el botón verde."""
        try:
            import tools_pc, vision
            captura = tools_pc._captura_principal()
            r = vision.preguntar(captura, "Mira esta captura de pantalla de Windows. ¿Hay una ventana emergente de llamada "
                                          "ENTRANTE de WhatsApp? Responde SOLO una palabra: VOZ si es una llamada de voz, "
                                          "VIDEO si es una videollamada, NADA si no hay ninguna llamada.").upper()
            registro.escribir(f"visión: tipo de llamada = {r[:40]!r}")
            if "VOZ" not in r or "VIDEO" in r or "NADA" in r:
                return False
            res = tools_pc.clic_visual("el botón verde para aceptar la llamada de voz entrante de WhatsApp "
                                       "(dice Accept Call o Aceptar)")
            registro.escribir(f"visión: {res[:150]}")
            return res.startswith("Hice clic")
        except Exception as e:
            registro.escribir(f"visión falló: {type(e).__name__}: {e}")
            return False

    def _atender(self, info):
        ok = self._intentar_aceptar()
        with self._lock:
            if self.estado != "aceptando":       # mientras tanto la tomaste tú, la rechazaste o colgaron
                self._hablando = False
                registro.escribir(f"la llamada cambió mientras aceptaba (estado {self.estado}); no hablo")
                return
            if not ok:
                self._hablando = False
                self._fijar("ignorando")         # sin silenciar: Jarvis sigue funcionando normal
            else:
                self._hablando = True
                self._fijar("jarvis")            # recién ahora se silencia la voz de Jarvis
        if not ok:
            self._escribir("Jarvis", "No logré contestar la llamada de WhatsApp. Si quieres saber por qué, di «diagnostica la llamada» "
                                     "o mira el archivo de registro llamadas.log.")
            if (info or {}).get("tipo") == "entrante":   # solo avisa si de verdad había una llamada visible
                self._notificar(info, f"{self._quien(info)} te está llamando por WhatsApp y no pude contestar.")
            return
        self._escribir("Jarvis", f"Contesté la llamada de {self._quien(info)}.")
        self._notificar(info, f"{self._quien(info)} te está llamando por WhatsApp. "
                        "Jarvis contestó y dijo que esperen o dejen un mensaje.")
        self.dormir(_cfg("LLAMADA_RETRASO_SALUDO", 2.5))   # deja que se establezca el audio antes de hablar
        saludo = _cfg("LLAMADA_SALUDO", "Hola, soy Jarvis.").format(usuario=self._usuario())
        conversa = self._conversar is not None and _cfg("LLAMADA_CONVERSAR", True)
        por_cable = True
        try:
            repeticiones = 1 if conversa else max(1, int(_cfg("LLAMADA_SALUDO_REPETIR", 2)))
            for n in range(repeticiones):
                if n:
                    self.dormir(1.5)
                    if self.estado != "jarvis" or self._colgar_pedido:
                        break
                resultado = self._hablar_llamada(saludo)
                registro.escribir(f"saludo {n + 1}: {resultado}")
                if isinstance(resultado, str) and resultado.startswith("parlantes"):
                    por_cable = False
                    self._escribir("Jarvis", "El saludo salió por los parlantes, no por el cable: " + resultado)
                    break   # repetir por los parlantes solo molestaría
        except Exception as e:
            registro.escribir(f"no pude decir el saludo: {type(e).__name__}: {e}")
        conversa = conversa and por_cable
        with self._lock:
            self._hablando = False
            if self.estado == "jarvis":
                self.hasta = self.reloj() + (0 if self._colgar_pedido else
                                             (_cfg("LLAMADA_CONVERSACION_MAX_SEG", 240) if conversa else _cfg("LLAMADA_PERMANENCIA_SEG", 45)))
        if conversa and not self._colgar_pedido:
            self._conversar_con_llamante(info)

    def _activa_para_jarvis(self) -> bool:
        """La llamada sigue siendo de Jarvis: no colgaron, no la tomaste tú y no se agotó el tiempo máximo."""
        if self.estado != "jarvis" or self._colgar_pedido:
            return False
        return not (self.hasta is not None and self.reloj() >= self.hasta)

    def _conversar_con_llamante(self, info):
        def hablar(texto):
            with self._lock:
                self._hablando = True      # mientras habla no se cuelga ni se da por terminada la llamada
            try:
                return self._hablar_llamada(texto)
            finally:
                with self._lock:
                    self._hablando = False
        try:
            r = self._conversar(info, hablar, self._activa_para_jarvis, self._escribir, self._avisar)
        except Exception as e:
            registro.escribir(f"error en la conversación: {type(e).__name__}: {e}")
            r = {"ok": False}
        with self._lock:
            if self.estado == "jarvis" and not self._colgar_pedido:
                # Fin de la conversación (despedida, silencio, tiempo agotado): se despide y cuelga. Si ni siquiera pudo
                # oír a quien llama, se queda el tiempo de siempre antes de despedirse.
                self.hasta = self.reloj() if r.get("ok") else self.reloj() + _cfg("LLAMADA_PERMANENCIA_SEG", 45)

    def _colgar_por_vision(self) -> bool:
        """La ventana de llamada en curso no expone el botón de colgar: se pone el mouse sobre ella (los controles de
        WhatsApp aparecen al pasar el mouse) y se busca el botón rojo mirando la pantalla."""
        try:
            import tools_pc
            centro = getattr(self.ui, "centro_llamada", lambda: None)()
            if centro:
                x, y, w, h = centro
                tools_pc.mover_mouse(int(x + w / 2), int(y + h / 2))
                self.dormir(0.8)
            res = tools_pc.clic_visual("el botón rojo para colgar o finalizar la llamada de WhatsApp en curso")
            registro.escribir(f"colgar por visión: {res[:150]}")
            return res.startswith("Hice clic")
        except Exception as e:
            registro.escribir(f"colgar por visión falló: {type(e).__name__}: {e}")
            return False

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
            except Exception as e:
                registro.escribir(f"colgar por UI Automation falló: {type(e).__name__}: {e}")
            registro.escribir(f"colgar por UI Automation: {ok}")
            if not ok and _cfg("LLAMADA_COLGAR_POR_VISION", True):
                ok = self._colgar_por_vision()
            if not ok:
                self._escribir("Jarvis", "No pude colgar la llamada; cuélgala tú.")
            with self._lock:
                if self.estado == "jarvis":
                    self._reset()

    # ---------- órdenes del usuario ----------
    def anunciar_usuario(self) -> str:
        info = self._buscar()   # fuera del lock: leer la pantalla puede tardar un par de segundos
        if info is _ERROR:      # no se pudo leer: se sigue como si no se viera nada todavía
            info = None
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
            if self.estado == "aceptando":
                return "Ya la estoy contestando."
            if self.estado in ("jarvis", "usuario"):
                return "Ya hay una llamada en curso."
            self.deadline = None
        ok = self._intentar_aceptar()     # fuera del candado: leer WhatsApp puede tardar y no debe congelar nada
        with self._lock:
            if not ok:
                if self.estado == "esperando":
                    self._reset()
                return ("No logré contestar la llamada de WhatsApp (no encontré el botón). "
                        "Di «diagnostica la llamada» o mira llamadas.log.")
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
        try:                                          # fuera del candado: puede tardar
            ok = self.ui.colgar() if est == "usuario" else self.ui.rechazar()
        except Exception as e:
            registro.escribir(f"rechazar/colgar falló: {type(e).__name__}: {e}")
        if not ok and est == "usuario" and _cfg("LLAMADA_COLGAR_POR_VISION", True):
            ok = self._colgar_por_vision()
        with self._lock:
            if est in ("esperando", "aceptando", "usuario") and self.estado == est:
                self._reset()
        if est == "usuario":
            return "Llamada colgada." if ok else "No pude colgar la llamada; cuélgala tú."
        return "Llamada rechazada." if ok else "No veo ninguna llamada que pueda rechazar."

    def lo_tomo_yo(self) -> str:
        with self._lock:
            if self.estado in ("esperando", "aceptando", "jarvis"):
                self.deadline, self.hasta = None, None
                self._fijar("usuario")
                return "Va, es toda tuya. No la contesto."
        return "No hay ninguna llamada pendiente."

    def probar_voz(self) -> str:
        """Dice el saludo por la salida de la llamada (el cable) SIN necesidad de una llamada, para ajustar el audio."""
        r = self._hablar_llamada("Prueba de voz de Jarvis para llamadas. Si me oyes por WhatsApp, todo está bien.")
        registro.escribir(f"prueba de voz: {r}")
        if isinstance(r, str) and r.startswith("cable"):
            return ("Hablé por el cable de audio. Si quien llama no lo oye, en WhatsApp → Ajustes → Voz y video el micrófono "
                    "debe ser «CABLE Output». Para oírlo tú, activa «Escuchar este dispositivo» en CABLE Output.")
        return f"No salió por el cable ({r}). Mira llamadas.log para ver el motivo."

    def diagnosticar(self, segundos: int = 30) -> str:
        """Observa la pantalla `segundos` segundos y reporta qué ventanas aparecen (para llamarte mientras tanto)."""
        if self._observando:
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
                self.dormir(1)
                try:
                    actual = list(self.ui.instantanea())
                except Exception as e:      # una lectura fallida no corta la observación
                    linea = f"(una lectura falló: {type(e).__name__}: {e})"
                    if linea not in vistas:
                        vistas.add(linea)
                        nuevas.append(linea)
                    continue
                for l in actual:
                    if l not in vistas:
                        vistas.add(l)
                        nuevas.append(l)
            partes = ["NUEVO durante la observación:"] + (nuevas or ["(nada: no apareció ninguna ventana nueva)"]) + \
                     ["", "Ya estaba antes:"] + base + ["", "Registro reciente (llamadas.log):"] + (registro.cola(15) or ["(vacío)"])
            informe = "\n".join(partes)
            ruta = None
            try:
                from pathlib import Path
                ruta = Path.home() / ".jarvis" / "diagnostico_llamada.txt"
                ruta.write_text(informe, encoding="utf-8")
            except Exception:
                ruta = None
            self._escribir("Jarvis", "Resultado de la observación (revisa que no haya nada privado antes de compartirlo):\n"
                           + informe[:3000] + (f"\n\nGuardado en {ruta}" if ruta else ""))
        except Exception as e:
            self._escribir("Jarvis", f"Falló la observación de llamadas: {type(e).__name__}: {e}")
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
        if _RE_PRUEBA_VOZ.search(t):
            return self.probar_voz()
        if _RE_PRUEBA_OIDO.search(t):
            return probar_escucha_llamada()
        if _RE_DIAGNOSTICO.search(t):
            return self.diagnosticar()
        if est in ("esperando", "aceptando", "jarvis", "usuario") or habla_llamada:
            if _RE_YO.search(t):
                return self.lo_tomo_yo()
            if _RE_RECHAZAR.search(t) and (est != "libre" or habla_llamada):
                return self.rechazar_usuario()
            if _RE_ACEPTAR.search(t) and (est != "libre" or habla_llamada):
                if est in ("jarvis", "usuario", "aceptando"):
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
    return voice.hablar_en_llamada(texto)


def _marcar_en_llamada(activo: bool):
    import voice
    if activo:
        voice.en_llamada.set()      # solo calla la voz; NO saca a Jarvis del modo conversación (parecía un «descansa»)
    else:
        voice.en_llamada.clear()


def obtener(escribir=None) -> Gestor:
    global _gestor
    if _gestor is None:
        _gestor = Gestor(hablar=_hablar_normal, hablar_llamada=_hablar_en_llamada,
                         escribir=escribir, en_llamada=_marcar_en_llamada, conversar=_conversar_llamada)
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


def _conversar_llamada(info, hablar, activo, escribir, avisar):
    import conversacion_llamada
    return conversacion_llamada.conversar(info, hablar, activo, escribir, avisar)


def probar_escucha_llamada() -> str:
    """Prueba cómo oye Jarvis a quien llama (escucha unos segundos lo que suena por tus parlantes). No necesita llamada."""
    import conversacion_llamada
    return conversacion_llamada.probar_escucha()


def probar_voz_llamada() -> str:
    """Prueba el audio que oiría quien llama (habla por el cable de audio virtual). No necesita una llamada."""
    return obtener().probar_voz()


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
    _t("probar_voz_llamada", "Prueba la voz de Jarvis hacia el cable de audio de las llamadas de WhatsApp", {}, []),
    _t("probar_escucha_llamada", "Prueba cómo oye Jarvis a quien llama en una llamada de WhatsApp (escucha unos segundos por los parlantes)", {}, []),
    _t("probar_aviso_celular", "Envía un aviso de prueba al celular del usuario", {}, []),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in SPEC}
