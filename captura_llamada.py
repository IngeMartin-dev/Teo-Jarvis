"""Oír a quien llama: captura el audio que WhatsApp reproduce por tus parlantes (loopback de Windows) y lo transcribe.

Quien llama se oye por la salida de audio que usa WhatsApp (tus parlantes o audífonos). Windows permite «grabar» esa salida
(WASAPI loopback) sin tocar el micrófono ni instalar nada más que la biblioteca `soundcard`. Cosas a saber:
- Se captura TODO lo que suene por ese dispositivo (música incluida): durante la llamada conviene no poner nada más.
- Mientras Jarvis habla, la captura se pausa (y un instante después) para no oírse a sí mismo.
- Para transcribir se usa el reconocimiento de voz de Google (el mismo que usa Jarvis con tu micrófono): el audio de quien
  llama viaja a Google solo durante la transcripción. No se guarda ningún audio en el disco.
Todo lo que depende de Windows está dentro de _bucle(), así que el resto se puede probar con audio sintético.
"""
import collections, queue, threading, time
import config, registro

TASA = 16000
BLOQUE = 0.1          # segundos por trozo de audio


class Oyente:
    def __init__(self):
        self._cola = queue.Queue(maxsize=600)
        self._hilo = None
        self._parar = threading.Event()
        self._pausado = False
        self._pausa_hasta = 0.0
        self.fallo = ""
        self.piso = 0.003      # nivel de ruido de fondo estimado
        self.nivel_max = 0.0   # el volumen más alto oído (para diagnóstico)

    # ---------- captura (solo Windows) ----------
    def iniciar(self):
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._parar.clear()
        self.fallo = ""
        listo = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, args=(listo,), daemon=True, name="oyente-llamada")
        self._hilo.start()
        listo.wait(8)
        if self.fallo:
            raise RuntimeError(self.fallo)

    def _bucle(self, listo):
        try:
            import numpy as np
            import soundcard as sc
            parte = (getattr(config, "LLAMADA_AUDIO_ENTRADA", "") or "").lower()
            altavoz = None
            if parte:
                altavoz = next((s for s in sc.all_speakers() if parte in s.name.lower()), None)
                if altavoz is None:
                    registro.escribir(f"oído: no encuentro la salida «{parte}»; uso la predeterminada")
            altavoz = altavoz or sc.default_speaker()
            mic = sc.get_microphone(id=str(altavoz.name), include_loopback=True)
            registro.escribir(f"oído: escuchando la salida «{altavoz.name}»")
            n = int(TASA * BLOQUE)
            with mic.recorder(samplerate=TASA, blocksize=n) as rec:
                listo.set()
                while not self._parar.is_set():
                    d = rec.record(numframes=n)
                    mono = d.mean(axis=1) if getattr(d, "ndim", 1) > 1 else d
                    if self._pausado or time.time() < self._pausa_hasta:
                        continue
                    rms = float(np.sqrt(np.mean(np.square(mono))))
                    pcm = (np.clip(mono, -1.0, 1.0) * 32767).astype("<i2").tobytes()
                    self._poner(rms, pcm)
        except Exception as e:   # noqa: BLE001
            self.fallo = f"{type(e).__name__}: {e}"
            registro.escribir(f"oído: error de captura: {self.fallo}")
        finally:
            listo.set()

    def _poner(self, rms: float, pcm: bytes):
        if self._cola.full():
            try:
                self._cola.get_nowait()
            except queue.Empty:
                pass
        self._cola.put((rms, pcm))

    def _vaciar(self):
        try:
            while True:
                self._cola.get_nowait()
        except queue.Empty:
            pass

    def pausar(self):
        """Mientras Jarvis habla: no captura (así no se oye a sí mismo)."""
        self._pausado = True
        self._vaciar()

    def reanudar(self):
        self._pausa_hasta = time.time() + 0.7   # el eco de los parlantes tarda un poco en apagarse
        self._pausado = False
        self._vaciar()

    def cerrar(self):
        self._parar.set()

    # ---------- detección de voz (independiente de Windows) ----------
    def escuchar(self, espera_max: float = 10.0, silencio_fin: float = 1.0, max_voz: float = 20.0):
        """Espera a que hable quien llama y devuelve su frase como audio PCM de 16 bits a 16 kHz, o None si no habló en
        `espera_max` segundos (o la captura falló). La frase termina tras `silencio_fin` segundos de silencio."""
        try:
            base = float(getattr(config, "LLAMADA_UMBRAL_VOZ", 0.01))
        except (TypeError, ValueError):
            base = 0.01
        previos = collections.deque(maxlen=6)
        voz, hablando, ruidosos, callado, esperado, dur = [], False, 0, 0.0, 0.0, 0.0
        while True:
            try:
                rms, pcm = self._cola.get(timeout=1.0)
                paso = BLOQUE
            except queue.Empty:
                if self.fallo or self._parar.is_set():
                    return None
                rms, pcm, paso = 0.0, b"", 1.0     # no llegó audio: cuenta como silencio
            self.nivel_max = max(self.nivel_max, rms)
            fuerte = rms > max(base, self.piso * 3)
            if not hablando:
                esperado += paso
                if pcm:
                    previos.append(pcm)
                if fuerte:
                    ruidosos += 1
                else:
                    ruidosos = 0
                    self.piso = 0.95 * self.piso + 0.05 * rms
                if ruidosos >= 3:                 # 0,3 s seguidos de voz: empezó a hablar
                    hablando, voz = True, list(previos)
                elif esperado >= espera_max:
                    return None
            else:
                if pcm:
                    voz.append(pcm)
                dur += paso
                callado = 0.0 if fuerte else callado + paso
                if callado >= silencio_fin or dur >= max_voz:
                    return b"".join(voz)


def a_texto(pcm: bytes) -> str:
    """Transcribe audio PCM de 16 bits a 16 kHz. '' si no se entendió. Lanza RuntimeError si el servicio no responde."""
    import speech_recognition as sr
    try:
        return sr.Recognizer().recognize_google(sr.AudioData(pcm, TASA, 2), language=getattr(config, "LANG", "es-CO")).strip()
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        raise RuntimeError(f"el reconocimiento de voz no respondió: {e}")
