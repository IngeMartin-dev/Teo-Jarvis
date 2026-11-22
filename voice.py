"""Voz: escucha la frase clave y habla las respuestas."""
import threading
import config

try:
    import speech_recognition as sr
    import pyttsx3
    OK = True
except ImportError:
    OK = False

_tts_lock = threading.Lock()


def hablar(texto: str):
    if not (OK and config.VOICE_ENABLED):
        return
    def _run():
        with _tts_lock:
            motor = pyttsx3.init()
            motor.say(texto)
            motor.runAndWait()
    threading.Thread(target=_run, daemon=True).start()


def escuchar_en_bucle(al_oir_comando, activo=lambda: True):
    """Escucha continuamente. Si oye la frase clave + comando, llama al_oir_comando(texto)."""
    if not OK:
        return
    rec = sr.Recognizer()
    mic = sr.Microphone()
    with mic as fuente:
        rec.adjust_for_ambient_noise(fuente, duration=1)
    while True:
        if not activo():
            continue
        try:
            with mic as fuente:
                audio = rec.listen(fuente, phrase_time_limit=8)
            texto = rec.recognize_google(audio, language=config.LANG).lower()  # reconocimiento vía Google (gratis)
        except Exception:
            continue
        for w in config.WAKE_PHRASES:
            if texto.startswith(w):
                comando = texto[len(w):].strip(" ,.")
                if not comando:
                    hablar("Dime.")
                    try:
                        with mic as fuente:
                            audio = rec.listen(fuente, timeout=6, phrase_time_limit=10)
                        comando = rec.recognize_google(audio, language=config.LANG)
                    except Exception:
                        break
                al_oir_comando(comando)
                break
