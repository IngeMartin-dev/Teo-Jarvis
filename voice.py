"""Voz: modo conversación continua + síntesis de voz.

Flujo: dices «Hola Jarvis» una vez -> queda en modo conversación y te escucha SIN que repitas
la frase de activación, hasta que digas «adiós Jarvis» / «eso es todo» (o pase CONVERSATION_TIMEOUT).
Mientras habla o piensa no escucha, para no oírse a sí mismo.
"""
import re, threading, time
import config

try:
    import speech_recognition as sr
    import pyttsx3
    OK = True
except ImportError:
    OK = False

ocupado = threading.Event()      # activo mientras Jarvis piensa o habla
conversando = threading.Event()  # activo en modo conversación
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
    if not (OK and config.VOICE_ENABLED):
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


def _es_fin(t: str) -> bool:
    return any(f in t for f in config.END_PHRASES)


def escuchar_en_bucle(al_oir_comando, activo=lambda: True):
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
