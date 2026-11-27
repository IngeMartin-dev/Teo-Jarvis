"""Voz: modo conversación continua + síntesis de voz.

Flujo: dices «Hola Jarvis» una vez -> queda en modo conversación y te escucha SIN que repitas
la frase de activación, hasta que digas «adiós Jarvis» / «eso es todo» (o pase CONVERSATION_TIMEOUT).
Mientras habla o piensa no escucha, para no oírse a sí mismo.
"""
import re, threading, time, wave
from pathlib import Path
import tempfile
import config

try:
    import speech_recognition as sr
    import pyttsx3
    OK = True
except ImportError:
    OK = False

ocupado = threading.Event()      # activo mientras Jarvis piensa o habla
conversando = threading.Event()  # activo en modo conversación
en_llamada = threading.Event()   # activo mientras hay una llamada de WhatsApp en curso: Jarvis no habla en voz alta
on_estado = lambda estado: None  # lo asigna main.py: "reposo" | "escuchando" | "pensando" | "hablando"
_lock = threading.Lock()
_WAKE = re.compile(config.WAKE_REGEX, re.I)


def set_estado(e: str):
    try:
        on_estado(e)
    except Exception:
        pass


def hablar(texto: str):
    """Habla en voz alta y espera a terminar."""
    if not (OK and config.VOICE_ENABLED) or en_llamada.is_set():
        return
    texto = re.sub(r"[*_`#]+", "", texto)[:500]
    with _lock:
        set_estado("hablando")
        try:
            motor = pyttsx3.init()
            motor.setProperty("rate", config.VOICE_RATE)
            for v in motor.getProperty("voices"):
                if "spanish" in v.name.lower() or "_es-" in v.id.lower():
                    motor.setProperty("voice", v.id)
                    break
            motor.say(texto)
            motor.runAndWait()
        except Exception:
            pass
        time.sleep(0.4)  # deja que se apague el eco antes de volver a escuchar


def _dispositivos_salida(parte: str) -> list:
    """Índices de TODOS los dispositivos de salida cuyo nombre contiene `parte` (p. ej. «CABLE Input»). Windows lista el
    mismo cable una vez por cada API de audio (MME, DirectSound, WASAPI...); se ordenan para probar primero MME."""
    import sounddevice as sd
    parte = parte.lower()
    try:
        apis = [a["name"] for a in sd.query_hostapis()]
    except Exception:
        apis = []
    orden = {"MME": 0, "Windows DirectSound": 1, "Windows WASAPI": 2}
    res = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0 and parte in d["name"].lower():
            api = apis[d["hostapi"]] if apis and d.get("hostapi") is not None and d["hostapi"] < len(apis) else ""
            res.append((orden.get(api, 9), i, d["name"], api))
    res.sort()
    return res


def _dispositivo_salida(parte: str):
    """Compatibilidad: el primer dispositivo que coincide, o None."""
    try:
        d = _dispositivos_salida(parte)
    except Exception:
        return None
    return d[0][1] if d else None


def _subir_volumen_propio() -> str:
    """Pone en 100 % y sin silencio TODAS las sesiones de audio de este programa, en todos los dispositivos de salida.
    El mezclador de Windows guarda un volumen por aplicación (a veces queda en 1 y no deja subirlo a mano). Necesita
    pycaw (opcional); si no está, solo lo anota. Nunca lanza errores."""
    try:
        import os
        from comtypes import CLSCTX_ALL
        from ctypes import POINTER, cast
        from pycaw.pycaw import AudioUtilities, IAudioSessionManager2, IAudioSessionControl2, ISimpleAudioVolume
        pid, cambios = os.getpid(), []
        enumerador = AudioUtilities.GetDeviceEnumerator()
        dispositivos = enumerador.EnumAudioEndpoints(0, 1)   # 0 = salidas, 1 = activos
        for i in range(dispositivos.GetCount()):
            try:
                dev = dispositivos.Item(i)
                gestor = cast(dev.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None), POINTER(IAudioSessionManager2))
                sesiones = gestor.GetSessionEnumerator()
                for j in range(sesiones.GetCount()):
                    ctl = sesiones.GetSession(j)
                    if ctl.QueryInterface(IAudioSessionControl2).GetProcessId() != pid:
                        continue
                    vol = ctl.QueryInterface(ISimpleAudioVolume)
                    antes, mudo = vol.GetMasterVolume(), vol.GetMute()
                    if antes < 0.99 or mudo:
                        vol.SetMasterVolume(1.0, None)
                        vol.SetMute(0, None)
                        cambios.append(f"dispositivo {i}: volumen {antes:.2f}{' (silenciado)' if mudo else ''} -> 1.00")
            except Exception as e:
                _log(f"volumen: dispositivo {i} no se pudo revisar ({type(e).__name__}: {e})")
        return "; ".join(cambios) or "sin cambios (ya estaba al máximo)"
    except ImportError:
        return "pycaw no está instalado (pip install pycaw); no puedo corregir el volumen"
    except Exception as e:
        return f"no pude corregir el volumen: {type(e).__name__}: {e}"


def _log(msg: str):
    try:
        import registro
        registro.escribir("voz: " + msg)
    except Exception:
        pass


def _sintetizar_wav(texto: str, ruta) -> tuple:
    motor = pyttsx3.init()
    motor.setProperty("rate", config.VOICE_RATE)
    for v in motor.getProperty("voices"):
        if "spanish" in v.name.lower() or "_es-" in v.id.lower():
            motor.setProperty("voice", v.id)
            break
    motor.save_to_file(texto, str(ruta))
    motor.runAndWait()
    with wave.open(str(ruta), "rb") as w:
        datos, canales, tasa, ancho = w.readframes(w.getnframes()), w.getnchannels(), w.getframerate(), w.getsampwidth()
    if ancho != 2:
        raise RuntimeError(f"formato de audio no compatible ({ancho * 8} bits)")
    if not datos:
        raise RuntimeError("la voz generó un audio vacío")
    return datos, canales, tasa


def hablar_en_llamada(texto: str) -> str:
    """Habla DENTRO de una llamada. Si LLAMADA_AUDIO_SALIDA apunta a un cable de audio virtual (VB-CABLE), manda la voz
    allí para que quien llama la oiga; si no, o si falla, habla por los parlantes. Anota todo en el registro de llamadas
    y devuelve «cable» o «parlantes: <motivo>»."""
    if not (OK and config.VOICE_ENABLED):
        return "voz desactivada"
    texto = re.sub(r"[*_`#]+", "", texto)[:500]
    destino = getattr(config, "LLAMADA_AUDIO_SALIDA", "")
    if not destino:
        _log("LLAMADA_AUDIO_SALIDA vacío: hablo por los parlantes")
        _hablar_forzado(texto)
        return "parlantes: sin cable configurado"
    ruta, motivo = None, ""
    try:
        import sounddevice as sd
        candidatos = _dispositivos_salida(destino)
        _log(f"dispositivos de salida que coinciden con «{destino}»: {[(i, n, a) for _o, i, n, a in candidatos]}")
        if not candidatos:
            raise RuntimeError(f"no encuentro ninguna salida de audio llamada «{destino}» (¿instalaste VB-CABLE y reiniciaste?)")
        with _lock:
            set_estado("hablando")
            ruta = Path(tempfile.gettempdir()) / "jarvis_llamada.wav"
            datos, canales, tasa = _sintetizar_wav(texto, ruta)
            _log(f"audio generado: {len(datos)} bytes, {canales} canal(es), {tasa} Hz")
            silencio = b"\x00" * (int(tasa * 0.6) * canales * 2)   # el cable «despierta» y se come el principio
            datos = silencio + datos + silencio
            ultimo = ""
            for _o, i, nombre, api in candidatos:
                try:
                    with sd.RawOutputStream(samplerate=tasa, channels=canales, dtype="int16", device=i) as salida:
                        _log("volumen de Jarvis: " + _subir_volumen_propio())   # la sesión de audio existe ya con el flujo abierto
                        salida.write(datos)
                    _log(f"reproducido por [{i}] {nombre} ({api})")
                    time.sleep(0.3)
                    return "cable"
                except Exception as e:
                    ultimo = f"[{i}] {nombre} ({api}): {type(e).__name__}: {e}"
                    _log("falló " + ultimo)
            raise RuntimeError("ningún dispositivo aceptó el audio; último error " + ultimo)
    except Exception as e:
        motivo = str(e)
        _log(f"no pude hablar por «{destino}»: {type(e).__name__}: {e}; uso los parlantes")
        print(f"[voz] No pude hablar por «{destino}» ({e}); uso los parlantes.")
    finally:
        if ruta is not None:
            try:
                ruta.unlink()
            except OSError:
                pass
    _hablar_forzado(texto)
    return "parlantes: " + motivo


def _hablar_forzado(texto: str):
    """Como hablar(), pero también durante una llamada."""
    with _lock:
        set_estado("hablando")
        try:
            motor = pyttsx3.init()
            motor.setProperty("rate", config.VOICE_RATE)
            for v in motor.getProperty("voices"):
                if "spanish" in v.name.lower() or "_es-" in v.id.lower():
                    motor.setProperty("voice", v.id)
                    break
            motor.say(texto)
            motor.runAndWait()
        except Exception:
            pass
        time.sleep(0.4)


def _es_fin(t: str) -> bool:
    return any(f in t for f in config.END_PHRASES)


def escuchar_en_bucle(al_oir_comando, activo=lambda: True, atajo=None):
    """atajo(texto) -> True si ya se atendió esa frase (p. ej. «contesta» durante una llamada) y no hay que procesarla."""
    if not OK:
        return
    rec = sr.Recognizer()
    rec.dynamic_energy_threshold = True
    rec.pause_threshold = 1.0
    mic = sr.Microphone()
    with mic as fuente:
        rec.adjust_for_ambient_noise(fuente, duration=1)
    ultimo = time.time()
    while True:
        if not activo():
            conversando.clear(); set_estado("reposo"); time.sleep(0.3); continue
        if ocupado.is_set():
            ultimo = time.time(); time.sleep(0.15); continue
        if conversando.is_set() and config.CONVERSATION_TIMEOUT and time.time() - ultimo > config.CONVERSATION_TIMEOUT:
            conversando.clear()
        set_estado("escuchando" if conversando.is_set() else "reposo")
        try:
            with mic as fuente:
                audio = rec.listen(fuente, timeout=4, phrase_time_limit=15)
            texto = rec.recognize_google(audio, language=config.LANG).lower().strip()
        except Exception:   # silencio, no entendió, o sin internet
            continue
        ultimo = time.time()
        if atajo is not None:
            try:
                if atajo(texto):
                    continue
            except Exception:
                pass
        m = _WAKE.match(texto)
        if conversando.is_set():
            if _es_fin(texto):
                conversando.clear()
                ocupado.set()
                try:
                    hablar("Aquí estaré cuando me necesites.")
                finally:
                    ocupado.clear()
                continue
            comando = texto[m.end():].strip(" ,.") if m else texto
            if comando:
                al_oir_comando(comando)
        else:
            if not m:
                continue
            conversando.set()
            comando = texto[m.end():].strip(" ,.")
            if comando:
                al_oir_comando(comando)
            else:
                ocupado.set()
                try:
                    hablar("Dime.")
                finally:
                    ocupado.clear()
