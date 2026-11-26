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


def _dispositivo_salida(parte: str):
    """Índice del dispositivo de salida de audio cuyo nombre contiene `parte` (p. ej. «CABLE Input»), o None."""
    import sounddevice as sd
    parte = parte.lower()
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0 and parte in d["name"].lower():
            return i
    return None


def hablar_en_llamada(texto: str):
    """Habla DENTRO de una llamada. Si LLAMADA_AUDIO_SALIDA apunta a un cable de audio virtual (VB-CABLE), manda la voz
    allí para que quien llama la oiga limpia; si no, habla por los parlantes (el micrófono apenas la capta)."""
    if not (OK and config.VOICE_ENABLED):
        return
    texto = re.sub(r"[*_`#]+", "", texto)[:500]
    destino = getattr(config, "LLAMADA_AUDIO_SALIDA", "")
    if not destino:
        _hablar_forzado(texto)
        return
    ruta = None
    try:
        import sounddevice as sd
        indice = _dispositivo_salida(destino)
        if indice is None:
            raise RuntimeError(f"no encuentro la salida de audio «{destino}»")
        with _lock:
            set_estado("hablando")
            ruta = Path(tempfile.gettempdir()) / "jarvis_llamada.wav"
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
                raise RuntimeError("formato de audio no compatible")
            with sd.RawOutputStream(samplerate=tasa, channels=canales, dtype="int16", device=indice) as salida:
                salida.write(datos)
            time.sleep(0.3)
    except Exception as e:
        print(f"[voz] No pude hablar por «{destino}» ({e}); uso los parlantes.")
        _hablar_forzado(texto)
    finally:
        if ruta is not None:
            try:
                ruta.unlink()
            except OSError:
                pass


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
