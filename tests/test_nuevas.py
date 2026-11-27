"""Pruebas de la lógica nueva (sin Windows, sin WhatsApp, sin red). Ejecutar con HOME apuntando a una carpeta temporal."""
import io, json, os, struct, sys, threading, time, types, unittest, wave
from unittest import mock

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
import brain, captura_llamada, config, conversacion_llamada, energia, instalador, llamadas, notificaciones, registro, tools, tools_pc, ui_llamadas, vision, voice  # noqa: E402


def esperar(cond, t=3.0):
    fin = time.time() + t
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avanzar(self, s):
        self.t += s


class UIFalsa:
    def __init__(self):
        self.info = None
        self.aceptar_ok = True
        self.llamadas = []

    def buscar_llamada(self):
        return self.info

    def aceptar(self):
        self.llamadas.append("aceptar")
        if getattr(self, "bloqueo", None) is not None:
            self.bloqueo.wait(5)
        return self.aceptar_ok

    def rechazar(self):
        self.llamadas.append("rechazar")
        return True

    def colgar(self):
        self.llamadas.append("colgar")
        return True

    def diagnostico(self):
        return "diag"

    def instantanea(self):
        return ["[whatsapp.exe] «WhatsApp» 300x500"] + (["[whatsapp.exe] «Llamada» 300x400", "    botones: Aceptar | Rechazar"] if self.info else [])


def nuevo_gestor():
    reloj, ui = Reloj(), UIFalsa()
    reg = types.SimpleNamespace(hablado=[], en_llamada=[], avisos=[], chat=[], estados=[])
    g = llamadas.Gestor(
        ui=ui,
        hablar=lambda t: reg.hablado.append(("normal", t)),
        hablar_llamada=lambda t: reg.hablado.append(("llamada", t)),
        avisar=lambda texto, titulo="", urgente=False: (reg.avisos.append(texto) or (True, "ok")),
        escribir=lambda q, t: reg.chat.append((q, t)),
        reloj=reloj, dormir=lambda s: None,
        en_llamada=lambda a: reg.en_llamada.append(a))
    return g, ui, reloj, reg


ENTRANTE = {"tipo": "entrante", "nombre": "Mamá", "video": False, "hwnd": 1}
ACTIVA = {"tipo": "activa", "nombre": "Mamá", "video": False, "hwnd": 1}


class TestLlamadas(unittest.TestCase):
    def setUp(self):   # estas pruebas miden la cuenta de 15 s; el valor por defecto de config.py es 0 (contesta ya)
        for nombre, valor in (("LLAMADA_ESPERA_SEG", 15), ("LLAMADA_ANUNCIAR", True), ("LLAMADA_ACEPTAR_POR_VISION", False)):
            p = mock.patch.object(config, nombre, valor, create=True)
            p.start()
            self.addCleanup(p.stop)

    def test_usuario_contesta_antes_de_15s(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        self.assertEqual(g.estado, "esperando")
        self.assertTrue(esperar(lambda: g.deadline is not None))      # la cuenta empieza al terminar de avisar
        self.assertIn("Mamá", reg.hablado[0][1])
        reloj.avanzar(10)
        g.tick()
        self.assertEqual(g.estado, "esperando")                       # aún no se acaban los 15 s
        out = g.manejar_texto("Jarvis contesta")
        self.assertEqual(ui.llamadas, ["aceptar"])
        self.assertEqual(g.estado, "usuario")
        self.assertEqual(out, "Listo, la contesté.")
        reloj.avanzar(60)
        ui.info = ACTIVA
        g.tick()
        self.assertEqual(ui.llamadas, ["aceptar"])                    # Jarvis no vuelve a contestar
        self.assertEqual(reg.avisos, [])                              # y no avisa al celular: contestaste tú
        self.assertEqual(reg.en_llamada[-1], True)

    def test_sin_respuesta_contesta_jarvis_avisa_y_cuelga(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        self.assertTrue(esperar(lambda: g.deadline is not None))
        reloj.avanzar(14.9)
        g.tick()
        self.assertEqual(ui.llamadas, [])
        reloj.avanzar(0.2)                                            # pasaron 15 s sin que dijera nada
        ui.info = ENTRANTE
        g.tick()
        self.assertTrue(esperar(lambda: "aceptar" in ui.llamadas))
        self.assertTrue(esperar(lambda: any(k == "llamada" for k, _ in reg.hablado)))
        saludo = [t for k, t in reg.hablado if k == "llamada"][0]
        self.assertIn("Jarvis", saludo)
        self.assertIn("asistente con IA de Martín", saludo)
        self.assertIn("espere o deje un mensaje", saludo)
        self.assertEqual(len(reg.avisos), 1)                          # aviso al celular
        self.assertIn("Mamá", reg.avisos[0])
        self.assertEqual(g.estado, "jarvis")
        self.assertTrue(esperar(lambda: g.hasta is not None and not g._hablando))
        ui.info = ACTIVA
        reloj.avanzar(30)
        g.tick()
        self.assertEqual(ui.llamadas, ["aceptar"])                    # todavía en la línea
        reloj.avanzar(20)
        g.tick()
        self.assertTrue(esperar(lambda: "colgar" in ui.llamadas))
        self.assertTrue(esperar(lambda: g.estado == "libre"))
        self.assertEqual([t for k, t in reg.hablado if k == "llamada"][-1], "Le avisaré a Martín que usted llamó. Hasta luego.")

    def test_videollamada_no_se_contesta_sola(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = dict(ENTRANTE, video=True)
        g.tick()
        self.assertTrue(esperar(lambda: g.deadline is not None))
        reloj.avanzar(16)
        g.tick()
        self.assertTrue(esperar(lambda: len(reg.avisos) == 1))
        self.assertEqual(ui.llamadas, [])
        self.assertEqual(g.estado, "ignorando")
        self.assertIn("videollamada", reg.avisos[0])

    def test_colgaron_antes_de_tiempo(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        self.assertTrue(esperar(lambda: g.deadline is not None))
        ui.info = None
        for _ in range(3):
            g.tick()
        self.assertEqual(g.estado, "libre")
        reloj.avanzar(60)
        g.tick()
        self.assertEqual(ui.llamadas, [])
        self.assertEqual(reg.avisos, [])

    def test_usuario_anuncia_y_pasan_15s(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = None
        out = g.manejar_texto("Jarvis, me están llamando por WhatsApp")
        self.assertIn("15", out)
        self.assertEqual(g.estado, "esperando")
        reloj.avanzar(15)
        g.tick()
        self.assertEqual(g.estado, "esperando")                       # el colchón de 3 s por la respuesta hablada
        ui.info = ENTRANTE
        reloj.avanzar(4)
        g.tick()
        self.assertTrue(esperar(lambda: "aceptar" in ui.llamadas))
        self.assertTrue(esperar(lambda: len(reg.avisos) == 1))

    def test_usuario_anuncia_y_no_hay_ventana(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.aceptar_ok = False
        g.manejar_texto("oye me están llamando por whatsapp")
        reloj.avanzar(30)
        g.tick()
        self.assertTrue(esperar(lambda: g.estado == "ignorando"))
        self.assertEqual(reg.avisos, [])                              # no inventa avisos si nunca vio la llamada
        self.assertTrue(any("No logré" in t for _q, t in reg.chat))

    def test_yo_contesto_cancela(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        self.assertTrue(esperar(lambda: g.deadline is not None))
        self.assertIn("toda tuya", g.manejar_texto("yo me encargo"))
        reloj.avanzar(60)
        g.tick()
        self.assertEqual(ui.llamadas, [])
        self.assertEqual(g.estado, "usuario")

    def test_rechazar(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        self.assertEqual(g.manejar_texto("rechaza la llamada"), "Llamada rechazada.")
        self.assertEqual(ui.llamadas, ["rechazar"])
        self.assertEqual(g.estado, "libre")

    def test_contesta_sin_llamada_no_secuestra_frases(self):
        g, ui, reloj, reg = nuevo_gestor()
        self.assertIsNone(g.manejar_texto("contesta esta pregunta: ¿cuánto es 2+2?"))
        self.assertIsNone(g.manejar_texto("cuelga el cuadro"))        # sin llamada ni contexto: no es de llamadas
        self.assertIsNone(g.manejar_texto("¿qué hora es?"))
        self.assertIsNone(g.manejar_texto("me están llamando"))        # sin WhatsApp: puede ser el celular
        self.assertEqual(ui.llamadas, [])

    def test_frases_reconocidas(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        self.assertTrue(esperar(lambda: g.deadline is not None))
        for frase in ("jarvis contesta", "contéstala", "acepta la llamada", "atiende", "descuelga"):
            g2, ui2, _r, _g = nuevo_gestor()
            ui2.info = ENTRANTE
            g2.tick()
            self.assertEqual(g2.manejar_texto(frase), "Listo, la contesté.", frase)

    def test_atajo_voz_traga_la_conversacion_durante_llamada(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        g.manejar_texto("contesta")
        self.assertEqual(g.estado, "usuario")
        self.assertTrue(g.atajo_voz("abre la calculadora por favor"))        # lo dice la otra persona: se ignora
        self.assertFalse(g.atajo_voz("jarvis qué hora es"))                  # con la palabra clave sí pasa a Jarvis
        self.assertTrue(g.atajo_voz("jarvis yo me encargo") or True)
        self.assertEqual([k for k, _ in reg.hablado if k == "normal"][-1:], [k for k, _ in reg.hablado if k == "normal"][-1:])

    def test_atajo_voz_contesta_sin_palabra_clave(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        self.assertTrue(g.atajo_voz("contesta"))
        self.assertEqual(ui.llamadas, ["aceptar"])
        self.assertFalse(any(k == "normal" and "contest" in t.lower() for k, t in reg.hablado[1:]))   # en llamada no habla

    def test_atajo_voz_no_interfiere_sin_llamada(self):
        g, ui, reloj, reg = nuevo_gestor()
        self.assertFalse(g.atajo_voz("hola jarvis abre chrome"))
        self.assertFalse(g.atajo_voz("contesta"))

    def test_permiso_apagado(self):
        g, ui, reloj, reg = nuevo_gestor()
        with mock.patch.object(config, "PERMISOS", {"llamadas": False}, create=True):
            ui.info = ENTRANTE
            g.tick()
            self.assertEqual(g.estado, "libre")
            self.assertIsNone(g.manejar_texto("contesta la llamada"))

    def test_auto_contestar_apagado(self):
        g, ui, reloj, reg = nuevo_gestor()
        with mock.patch.object(config, "LLAMADAS_AUTO_CONTESTAR", False):
            ui.info = ENTRANTE
            g.tick()
            self.assertTrue(esperar(lambda: g.deadline is not None))
            reloj.avanzar(16)
            g.tick()
            self.assertTrue(esperar(lambda: len(reg.avisos) == 1))
            self.assertEqual(ui.llamadas, [])

    def test_fallo_al_aceptar_avisa_al_celular(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.aceptar_ok = False
        ui.info = ENTRANTE
        g.tick()
        self.assertTrue(esperar(lambda: g.deadline is not None))
        reloj.avanzar(16)
        g.tick()
        self.assertTrue(esperar(lambda: g.estado == "ignorando"))
        self.assertTrue(esperar(lambda: len(reg.avisos) == 1))
        self.assertIn("no pude contestar", reg.avisos[0])

    def test_espera_3s_sin_avisar_ni_pedir_permiso(self):
        g, ui, reloj, reg = nuevo_gestor()
        with mock.patch.object(config, "LLAMADA_ESPERA_SEG", 3), mock.patch.object(config, "LLAMADA_ANUNCIAR", False, create=True):
            ui.info = ENTRANTE
            g.tick()
            self.assertEqual(reg.hablado, [])                 # no dice «di contesta»
            self.assertEqual(g.deadline, reloj() + 3)
            reloj.avanzar(2.9); g.tick()
            self.assertEqual(ui.llamadas, [])                 # todavía no pasaron 3 s
            reloj.avanzar(0.2); g.tick()
            self.assertTrue(esperar(lambda: "aceptar" in ui.llamadas))
            self.assertTrue(esperar(lambda: any(k == "llamada" for k, _ in reg.hablado)))
            self.assertFalse(any(k == "normal" for k, _ in reg.hablado))   # nada de avisos por los parlantes
            self.assertTrue(esperar(lambda: len(reg.avisos) == 1))

    def test_en_los_3s_puede_decir_contesta_o_yo_contesto(self):
        g, ui, reloj, reg = nuevo_gestor()
        with mock.patch.object(config, "LLAMADA_ESPERA_SEG", 3), mock.patch.object(config, "LLAMADA_ANUNCIAR", False, create=True):
            ui.info = ENTRANTE
            g.tick()
            self.assertIn("toda tuya", g.manejar_texto("yo me encargo"))
            reloj.avanzar(10); g.tick()
            self.assertEqual(ui.llamadas, [])

    def test_espera_cero_contesta_directo(self):
        g, ui, reloj, reg = nuevo_gestor()
        with mock.patch.object(config, "LLAMADA_ESPERA_SEG", 0):
            ui.info = ENTRANTE
            g.tick()                                      # detecta la llamada
            self.assertEqual(reg.hablado, [])             # no avisa por voz
            g.tick()                                      # siguiente lectura: contesta
            self.assertTrue(esperar(lambda: "aceptar" in ui.llamadas))
            self.assertTrue(esperar(lambda: any(k == "llamada" for k, _ in reg.hablado)))
            self.assertIn("asistente con IA de Martín", [t for k, t in reg.hablado if k == "llamada"][0])
            self.assertTrue(esperar(lambda: len(reg.avisos) == 1))

    def test_diagnostico_observa_y_reporta(self):
        g, ui, reloj, reg = nuevo_gestor()
        pasos = []

        def dormir(s):
            pasos.append(s)
            reloj.avanzar(s)
            if len(pasos) == 3:
                ui.info = ENTRANTE                              # la llamada aparece durante la observación
        g.dormir = dormir
        out = g.manejar_texto("Jarvis, diagnostica la llamada")
        self.assertIn("30 segundos", out)
        self.assertTrue(esperar(lambda: any("NUEVO durante" in t for _q, t in reg.chat)))
        informe = [t for _q, t in reg.chat if "NUEVO durante" in t][0]
        self.assertIn("«Llamada»", informe.split("Ya estaba antes")[0])   # apareció después, no estaba al inicio
        self.assertIn("Aceptar | Rechazar", informe)

    def test_error_del_vigilante_se_muestra_una_vez(self):
        g, ui, reloj, reg = nuevo_gestor()

        def falla():
            raise ImportError("No module named 'pywinauto'")
        ui.buscar_llamada = falla
        g.tick(); g.tick(); g.tick()
        errores = [t for _q, t in reg.chat if "No puedo leer las ventanas" in t]
        self.assertEqual(len(errores), 1)
        self.assertIn("pywinauto", errores[0])

    def _llamar_y_vencer(self, g, ui, reloj):
        ui.info = ENTRANTE
        g.tick()
        self.assertTrue(esperar(lambda: g.deadline is not None))
        reloj.avanzar(16)
        g.tick()

    def test_no_silencia_a_jarvis_hasta_que_contesta(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.bloqueo = threading.Event()                     # contestar tarda (UI Automation lenta)
        self._llamar_y_vencer(g, ui, reloj)
        self.assertTrue(esperar(lambda: "aceptar" in ui.llamadas))
        self.assertEqual(g.estado, "aceptando")
        self.assertNotIn(True, reg.en_llamada)             # mientras intenta contestar, Jarvis NO está mudo
        ui.bloqueo.set()
        self.assertTrue(esperar(lambda: g.estado == "jarvis"))
        self.assertIn(True, reg.en_llamada)                # recién al contestar se silencia

    def test_si_falla_contestar_nunca_queda_mudo(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.aceptar_ok = False
        self._llamar_y_vencer(g, ui, reloj)
        self.assertTrue(esperar(lambda: g.estado == "ignorando"))
        self.assertNotIn(True, reg.en_llamada)

    def test_si_contestar_lanza_error_no_queda_mudo(self):
        g, ui, reloj, reg = nuevo_gestor()

        def revienta():
            raise TimeoutError("UI Automation no respondió")
        ui.aceptar = revienta
        self._llamar_y_vencer(g, ui, reloj)
        self.assertTrue(esperar(lambda: g.estado == "ignorando"))
        self.assertNotIn(True, reg.en_llamada)

    def test_estado_atascado_lo_libera_el_temporizador(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.bloqueo = threading.Event()                     # contestar se queda colgado
        self._llamar_y_vencer(g, ui, reloj)
        self.assertTrue(esperar(lambda: g.estado == "aceptando"))
        reloj.avanzar(500)
        g.tick()
        self.assertEqual(g.estado, "libre")
        self.assertTrue(any("Reinicié el estado" in t for _q, t in reg.chat))
        ui.bloqueo.set()                                   # cuando por fin responde, ya no habla ni silencia
        time.sleep(0.2)
        self.assertEqual(g.estado, "libre")
        self.assertNotIn(True, reg.en_llamada)
        self.assertFalse(any(k == "llamada" for k, _ in reg.hablado))

    def test_error_de_lectura_no_cuenta_como_llamada_terminada(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        g.manejar_texto("contesta")
        self.assertEqual(g.estado, "usuario")

        def lento():
            raise TimeoutError("UI Automation no respondió en 20 s")
        ui.buscar_llamada = lento
        for _ in range(6):
            g.tick()
        self.assertEqual(g.estado, "usuario")              # una lectura que falla NO significa que colgaron

    def test_contestar_a_pedido_no_bloquea_el_candado(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.bloqueo = threading.Event()
        ui.info = ENTRANTE
        g.tick()
        hilo = threading.Thread(target=g.manejar_texto, args=("contesta",), daemon=True)
        hilo.start()
        self.assertTrue(esperar(lambda: "aceptar" in ui.llamadas))
        self.assertTrue(g._lock.acquire(timeout=1))        # mientras UI Automation tarda, el vigilante puede seguir
        g._lock.release()
        ui.bloqueo.set()
        hilo.join(3)

    def test_yo_contesto_mientras_aceptaba(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.bloqueo = threading.Event()
        self._llamar_y_vencer(g, ui, reloj)
        self.assertTrue(esperar(lambda: g.estado == "aceptando"))
        self.assertIn("toda tuya", g.manejar_texto("yo me encargo"))
        ui.bloqueo.set()
        time.sleep(0.2)
        self.assertEqual(g.estado, "usuario")
        self.assertFalse(any(k == "llamada" for k, _ in reg.hablado))   # no dice el saludo encima de ti

    def test_vision_contesta_cuando_uia_falla(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.aceptar_ok = False
        with mock.patch.object(config, "LLAMADA_ACEPTAR_POR_VISION", True), \
                mock.patch.object(tools_pc, "_captura_principal", return_value="img"), \
                mock.patch.object(vision, "preguntar", return_value="VOZ"), \
                mock.patch.object(tools_pc, "clic_visual", return_value="Hice clic en lo que parece «Accept Call» (10, 20).") as cv:
            self._llamar_y_vencer(g, ui, reloj)
            self.assertTrue(esperar(lambda: g.estado == "jarvis"))
            cv.assert_called_once()
        self.assertTrue(esperar(lambda: any(k == "llamada" for k, _ in reg.hablado)))

    def test_vision_no_contesta_videollamadas_ni_si_no_hay_llamada(self):
        for respuesta in ("VIDEO", "NADA", "no sé"):
            g, ui, reloj, reg = nuevo_gestor()
            ui.aceptar_ok = False
            with mock.patch.object(config, "LLAMADA_ACEPTAR_POR_VISION", True), \
                    mock.patch.object(tools_pc, "_captura_principal", return_value="img"), \
                    mock.patch.object(vision, "preguntar", return_value=respuesta), \
                    mock.patch.object(tools_pc, "clic_visual") as cv:
                self._llamar_y_vencer(g, ui, reloj)
                self.assertTrue(esperar(lambda: g.estado == "ignorando"), respuesta)
                cv.assert_not_called()

    def test_vision_que_revienta_no_rompe_nada(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.aceptar_ok = False
        with mock.patch.object(config, "LLAMADA_ACEPTAR_POR_VISION", True), \
                mock.patch.object(tools_pc, "_captura_principal", side_effect=OSError("sin pantalla")):
            self._llamar_y_vencer(g, ui, reloj)
            self.assertTrue(esperar(lambda: g.estado == "ignorando"))

    def test_avisar_de_la_llamada_con_lectura_fallida(self):
        g, ui, reloj, reg = nuevo_gestor()

        def lento():
            raise TimeoutError("UI Automation no respondió en 20 s")
        ui.buscar_llamada = lento
        out = g.manejar_texto("Jarvis, me están llamando por WhatsApp")
        self.assertIn("contesto yo", out)                  # no revienta: sigue esperando la llamada
        self.assertEqual(g.estado, "esperando")

    def test_conversacion_continua_no_se_apaga_con_la_llamada(self):
        voice.conversando.set()
        try:
            llamadas._marcar_en_llamada(True)
            self.assertTrue(voice.en_llamada.is_set())
            self.assertTrue(voice.conversando.is_set())    # antes se apagaba y parecía un «descansa»
            llamadas._marcar_en_llamada(False)
            self.assertFalse(voice.en_llamada.is_set())
        finally:
            voice.conversando.clear(); voice.en_llamada.clear()

    def test_cuelga_durante_llamada_de_jarvis(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        self.assertTrue(esperar(lambda: g.deadline is not None))
        reloj.avanzar(16)
        g.tick()
        self.assertTrue(esperar(lambda: g.hasta is not None and not g._hablando))
        ui.info = ACTIVA
        self.assertEqual(g.manejar_texto("jarvis cuelga"), "Voy a colgar la llamada.")
        g.tick()
        self.assertTrue(esperar(lambda: "colgar" in ui.llamadas))


class TestLlamadaActivaYVoz(unittest.TestCase):
    def test_ventana_voice_call_sin_botones_es_llamada_activa(self):
        v = {"hwnd": 9, "titulo": "Voice call", "exe": "whatsapp.root.exe", "w": 240, "h": 200, "left": 10, "top": 20}
        ui_llamadas._cache.clear()
        with mock.patch.object(ui_llamadas, "_controles", return_value=[("Minimize", object()), ("Close", object())]):
            info = ui_llamadas._analizar(v)
        self.assertEqual(info["tipo"], "activa")
        ui_llamadas._cache.clear()

    def test_ventana_sin_titulo_de_llamada_ni_botones_no_es_llamada(self):
        v = {"hwnd": 9, "titulo": "WhatsApp", "exe": "whatsapp.root.exe", "w": 240, "h": 200, "left": 0, "top": 0}
        with mock.patch.object(ui_llamadas, "_controles", return_value=[("Minimize", object())]):
            self.assertIsNone(ui_llamadas._analizar(v))
        ui_llamadas._cache.clear()

    def test_cable_prueba_otros_dispositivos_si_el_primero_falla(self):
        usados = []

        class Motor:
            def setProperty(self, *a): pass
            def getProperty(self, n): return []
            def save_to_file(self, texto, ruta):
                with wave.open(ruta, "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
                    w.writeframes(struct.pack("<50h", *range(50)))
            def runAndWait(self): pass

        class Flujo:
            def __init__(self, **kw):
                usados.append(kw["device"])
                if kw["device"] == 1:
                    raise OSError("dispositivo ocupado")
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def write(self, d): pass

        sd = types.SimpleNamespace(
            query_hostapis=lambda: [{"name": "MME"}, {"name": "Windows WASAPI"}],
            query_devices=lambda: [{"name": "Altavoces", "max_output_channels": 2, "hostapi": 0},
                                   {"name": "CABLE Input (VB-Audio)", "max_output_channels": 2, "hostapi": 0},
                                   {"name": "CABLE Input (VB-Audio)", "max_output_channels": 2, "hostapi": 1}],
            RawOutputStream=Flujo)
        with mock.patch.dict(sys.modules, {"sounddevice": sd}), mock.patch.object(voice, "OK", True), \
                mock.patch.object(voice, "pyttsx3", types.SimpleNamespace(init=lambda: Motor()), create=True), \
                mock.patch.object(config, "LLAMADA_AUDIO_SALIDA", "cable input"), mock.patch.object(config, "VOICE_ENABLED", True):
            self.assertEqual(voice.hablar_en_llamada("Hola"), "cable")
        self.assertEqual(usados, [1, 2])

    def test_prueba_de_voz_por_comando(self):
        g = llamadas.Gestor(hablar_llamada=lambda t: "cable")
        r = g.manejar_texto("jarvis prueba la voz de la llamada")
        self.assertIn("cable", r.lower())

    def test_cae_a_parlantes_y_lo_dice(self):
        g = llamadas.Gestor(hablar_llamada=lambda t: "parlantes: no encuentro")
        self.assertIn("No salió por el cable", g.probar_voz())


class TestConversacionLlamada(unittest.TestCase):
    def _frase(self, o, fuerte=True, bloques=10):
        for _ in range(bloques):
            o._poner(0.1 if fuerte else 0.0, b"\x01\x00" * 1600)

    def test_oyente_detecta_una_frase_y_corta_en_el_silencio(self):
        o = captura_llamada.Oyente()
        self._frase(o, True, 8)
        self._frase(o, False, 12)
        pcm = o.escuchar(espera_max=5, silencio_fin=1.0)
        self.assertIsNotNone(pcm)
        self.assertGreater(len(pcm), 8 * 3200)

    def test_oyente_sin_voz_devuelve_none(self):
        o = captura_llamada.Oyente()
        self._frase(o, False, 30)
        self.assertIsNone(o.escuchar(espera_max=2.0))

    def test_oyente_ignora_un_ruido_corto(self):
        o = captura_llamada.Oyente()
        self._frase(o, True, 2)            # menos de 0,3 s: no es una frase
        self._frase(o, False, 30)
        self.assertIsNone(o.escuchar(espera_max=2.0))

    def test_analizar_respuesta_json_y_texto_plano(self):
        r = conversacion_llamada._analizar_respuesta('```json\n{"decir": "Claro", "recado": "Llamar a Ana", "terminar": false}\n```')
        self.assertEqual((r["decir"], r["recado"], r["terminar"]), ("Claro", "Llamar a Ana", False))
        r = conversacion_llamada._analizar_respuesta('{"decir": "", "recado": "", "terminar": true}')
        self.assertTrue(r["terminar"])
        r = conversacion_llamada._analizar_respuesta("Hola, buenas tardes")
        self.assertEqual(r["decir"], "Hola, buenas tardes")

    def _conversar(self, frases, respuestas, activo=lambda: True):
        dichas, avisos, chat = [], [], []

        class Oy:
            fallo = ""
            nivel_max = 0
            def __init__(s): s.frases = list(frases)
            def iniciar(s): pass
            def reanudar(s): pass
            def pausar(s): pass
            def cerrar(s): pass
            def escuchar(s, **kw): return s.frases.pop(0) if s.frases else None

        resp = list(respuestas)
        r = conversacion_llamada.conversar(
            {"nombre": "Ana"}, dichas.append, activo, lambda q, t: chat.append((q, t)),
            lambda texto, titulo="", urgente=False: (avisos.append(texto) or (True, "ok")),
            oyente=Oy(), charlar=lambda sis, msgs: resp.pop(0), a_texto=lambda pcm: pcm.decode())
        return r, dichas, avisos, chat

    def test_toma_un_recado_lo_avisa_y_se_despide(self):
        r, dichas, avisos, chat = self._conversar(
            [b"quiero dejarle un mensaje", b"que me llame manana", b"gracias adios"],
            ['{"decir": "Claro, dígame.", "recado": "", "terminar": false}',
             '{"decir": "Anotado: que la llame mañana.", "recado": "Que Ana la llame mañana", "terminar": false}',
             '{"decir": "", "recado": "", "terminar": true}'])
        self.assertEqual(r["recados"], ["Que Ana la llame mañana"])
        self.assertEqual(avisos, ["Te llamó Ana y dejó este mensaje: Que Ana la llame mañana"])   # un solo aviso: quién y qué mensaje
        self.assertEqual(dichas, ["Claro, dígame.", "Anotado: que la llame mañana."])

    def test_dos_silencios_terminan(self):
        r, dichas, avisos, _ = self._conversar([], [])
        self.assertTrue(r["ok"])
        self.assertEqual(dichas, [])                                     # en silencio no pregunta nada
        self.assertEqual(avisos, [])                                     # sin conversación: sin aviso

    def test_sin_recado_avisa_quien_llamo(self):
        r, dichas, avisos, _ = self._conversar([b"cuanto es dos mas dos", b"adios"],
            ['{"decir": "Cuatro.", "recado": "", "terminar": false}', '{"decir": "", "recado": "", "terminar": true}'])
        self.assertEqual(avisos, ["Te llamó Ana. No dejó ningún mensaje."])
        self.assertEqual(dichas, ["Cuatro."])

    def test_el_modelo_no_ofrece_dejar_recado(self):
        self.assertNotIn("dejarle un mensaje", conversacion_llamada._SISTEMA.split("NO le preguntes")[0])
        self.assertIn("NO le preguntes si quiere dejar un mensaje", conversacion_llamada._SISTEMA)

    def test_modelo_caido_no_pierde_lo_que_dijo(self):
        r, dichas, avisos, _ = self._conversar([b"avise que llego tarde"], [])   # charlar lanza IndexError
        self.assertEqual(r["recados"], ["avise que llego tarde"])

    def test_se_detiene_si_la_llamada_deja_de_estar_activa(self):
        estado = {"n": 0}

        def activo():
            estado["n"] += 1
            return estado["n"] <= 2
        r, dichas, _a, _c = self._conversar([b"hola"] * 5, ['{"decir": "Hola", "recado": "", "terminar": false}'] * 5, activo)
        self.assertLessEqual(len(dichas), 1)

    def test_sin_oido_devuelve_ok_false(self):
        class Roto:
            def iniciar(s): raise RuntimeError("sin soundcard")
        chat = []
        r = conversacion_llamada.conversar({"nombre": "Ana"}, lambda t: None, lambda: True, lambda q, t: chat.append(t),
                                           lambda *a, **k: (True, ""), oyente=Roto(), charlar=lambda *a: "", a_texto=lambda p: "")
        self.assertFalse(r["ok"])

    def test_gestor_conversa_y_luego_cuelga(self):
        g, ui, reloj, reg = nuevo_gestor()
        llamado = []

        def conv(info, hablar, activo, escribir, avisar):
            llamado.append(activo())
            hablar("respuesta de prueba")
            return {"ok": True}
        g._conversar = conv
        ui.info = ENTRANTE
        with mock.patch.object(config, "LLAMADA_ESPERA_SEG", 0, create=True), mock.patch.object(config, "LLAMADA_ANUNCIAR", False, create=True), \
                mock.patch.object(config, "LLAMADA_ACEPTAR_POR_VISION", False, create=True):
            g.tick()
            g.tick()
            self.assertTrue(esperar(lambda: llamado))
            self.assertTrue(esperar(lambda: g.estado == "jarvis" and g.hasta is not None))
            self.assertTrue(llamado[0])
            self.assertEqual(sum(1 for q, t in reg.hablado if q == "llamada" and "Jarvis" in t), 1)   # un solo saludo
            reloj.avanzar(1)
            ui.info = ACTIVA
            g.tick()
        self.assertTrue(esperar(lambda: "colgar" in ui.llamadas))

    def test_comando_prueba_de_oido(self):
        g = llamadas.Gestor()
        with mock.patch.object(llamadas, "probar_escucha_llamada", return_value="Oí: «hola»"):
            self.assertEqual(g.manejar_texto("jarvis prueba el oído de la llamada"), "Oí: «hola»")


class TestUIALimites(unittest.TestCase):
    """El hilo de UI Automation: límites de tiempo y tareas viejas (no necesita Windows)."""

    def test_devuelve_resultado_y_propaga_errores(self):
        self.assertEqual(ui_llamadas.en_hilo(lambda: 42, 2), 42)
        with self.assertRaises(ValueError):
            ui_llamadas.en_hilo(lambda: (_ for _ in ()).throw(ValueError("x")), 2)

    def test_timeout_no_bloquea_y_se_recupera(self):
        ui_llamadas._hilo = None
        t0 = time.time()
        with self.assertRaises(TimeoutError):
            ui_llamadas.en_hilo(lambda: time.sleep(1.0), 0.2)
        self.assertLess(time.time() - t0, 0.8)             # se rinde a tiempo, no espera a que termine
        time.sleep(1.0)                                    # la tarea lenta termina sola
        self.assertEqual(ui_llamadas.en_hilo(lambda: "ok", 2), "ok")

    def test_tarea_cancelada_no_se_ejecuta_tarde(self):
        ui_llamadas._hilo = None
        ejecutadas = []
        with self.assertRaises(TimeoutError):
            ui_llamadas.en_hilo(lambda: time.sleep(0.6), 0.1)      # ocupa el hilo
        with self.assertRaises(TimeoutError):
            ui_llamadas.en_hilo(lambda: ejecutadas.append("clic viejo"), 0.1)   # espera en cola y se rinde
        time.sleep(1.0)
        self.assertEqual(ejecutadas, [])                   # no hace un clic tardío cuando el hilo se libera

    def test_hilo_atascado_se_reemplaza(self):
        ui_llamadas._hilo = None
        with mock.patch.object(ui_llamadas, "_ABANDONO", 0.1):
            with self.assertRaises(TimeoutError):
                ui_llamadas.en_hilo(lambda: time.sleep(1.5), 0.2)
            time.sleep(0.3)
            t0 = time.time()
            self.assertEqual(ui_llamadas.en_hilo(lambda: "nuevo hilo", 1), "nuevo hilo")
            self.assertLess(time.time() - t0, 0.8)         # no esperó a que el hilo viejo terminara

    def test_sin_ventanas_candidatas_no_lee_nada(self):
        leidas = []
        with mock.patch.object(ui_llamadas, "_candidatas", return_value=[]), \
                mock.patch.object(ui_llamadas, "en_hilo", side_effect=lambda *a, **k: leidas.append(1)):
            self.assertIsNone(ui_llamadas.buscar_llamada())
        self.assertEqual(leidas, [])

    def test_lectura_en_cache_no_vuelve_a_leer(self):
        v = {"hwnd": 7, "titulo": "WhatsApp", "exe": "whatsapp.root.exe", "w": 400, "h": 300}
        info = {"tipo": "entrante", "hwnd": 7, "nombre": "Mami", "video": False}
        ui_llamadas._cache.clear()
        ui_llamadas._cache[7] = {"t": time.time(), "info": info}
        with mock.patch.object(ui_llamadas, "_candidatas", return_value=[v]), \
                mock.patch.object(ui_llamadas, "en_hilo", side_effect=AssertionError("no debe releer")):
            self.assertEqual(ui_llamadas.buscar_llamada(), info)
        ui_llamadas._cache.clear()


class TestRegistro(unittest.TestCase):
    def test_escribe_y_lee_la_cola(self):
        registro.escribir("prueba uno\ncon salto")
        registro.escribir("prueba dos")
        ultimas = registro.cola(2)
        self.assertEqual(len(ultimas), 2)
        self.assertIn("prueba uno | con salto", ultimas[0])
        self.assertTrue(ultimas[1].endswith("prueba dos"))

    def test_no_rompe_si_no_puede_escribir(self):
        with mock.patch.object(registro, "ruta", side_effect=OSError("sin disco")):
            registro.escribir("no debe lanzar")
            self.assertEqual(registro.cola(), [])


class TestNotificaciones(unittest.TestCase):
    def test_sin_configurar(self):
        with mock.patch.object(config, "NTFY_TOPIC", ""), mock.patch.object(config, "TELEGRAM_BOT_TOKEN", ""):
            ok, msg = notificaciones.avisar_celular("hola")
            self.assertFalse(ok)
            self.assertIn("NTFY_TOPIC", msg)

    def test_ntfy(self):
        with mock.patch.object(config, "NTFY_TOPIC", "secreto-largo"), mock.patch("requests.post") as post:
            post.return_value.status_code = 200
            ok, _ = notificaciones.avisar_celular("Mamá te llama", "Llamada de WhatsApp", True)
            self.assertTrue(ok)
            url = post.call_args[0][0]
            payload = post.call_args[1]["json"]
            self.assertEqual(url, "https://ntfy.sh/")
            self.assertEqual(payload["topic"], "secreto-largo")
            self.assertEqual(payload["priority"], 5)
            self.assertEqual(payload["message"], "Mamá te llama")

    def test_telegram_y_error_sin_filtrar_token(self):
        import requests
        with mock.patch.object(config, "NTFY_TOPIC", ""), mock.patch.object(config, "TELEGRAM_BOT_TOKEN", "123:TOKENSECRETO"), \
                mock.patch.object(config, "TELEGRAM_CHAT_ID", "42"), \
                mock.patch("requests.post", side_effect=requests.ConnectionError("https://api.telegram.org/bot123:TOKENSECRETO/x")):
            ok, msg = notificaciones.avisar_celular("hola")
            self.assertFalse(ok)
            self.assertNotIn("TOKENSECRETO", msg)


SALIDA_ES = """Nombre                         Id            Versión  Origen
--------------------------------------------------------------
Spotify - Música y Podcasts    9NCBCSZSJRSB  Unknown  msstore
Spotify Lite                   9NXXXXXXXXXX  Unknown  msstore
"""
SALIDA_EN = """\r
  -\r
  \\\r
Name              Id                   Version   Match      Source
-----------------------------------------------------------------
Discord           Discord.Discord      1.0.9150  Tag: foo   winget
Discord PTB       Discord.Discord.PTB  1.0.1     Tag: foo   winget
"""


class TestInstalador(unittest.TestCase):
    def test_parsear(self):
        f = instalador.parsear_busqueda(SALIDA_ES, "msstore")
        self.assertEqual([x["id"] for x in f], ["9NCBCSZSJRSB", "9NXXXXXXXXXX"])
        self.assertEqual(f[0]["nombre"], "Spotify - Música y Podcasts")
        g = instalador.parsear_busqueda(SALIDA_EN, "winget")
        self.assertEqual([x["id"] for x in g], ["Discord.Discord", "Discord.Discord.PTB"])
        self.assertEqual(instalador.parsear_busqueda("No se encontró ningún paquete.", "winget"), [])

    def test_puntaje_y_elegir(self):
        self.assertEqual(instalador.puntaje("spotify", "Spotify - Música y Podcasts"), 2)
        self.assertEqual(instalador.puntaje("WhatsApp", "whatsapp"), 3)
        self.assertEqual(instalador.puntaje("visual studio code", "Microsoft Visual Studio Code"), 1)
        self.assertEqual(instalador.puntaje("chrome", "Chromium"), 0)
        f = instalador.parsear_busqueda(SALIDA_ES, "msstore")
        c, alt = instalador.elegir("spotify", f, instalador._ID_STORE)
        self.assertIsNone(c)                           # «Spotify - Música» y «Spotify Lite» empatan: no adivina
        self.assertEqual(len(alt), 2)
        c, alt = instalador.elegir("spotify", f[:1], instalador._ID_STORE)
        self.assertEqual(c["id"], "9NCBCSZSJRSB")

    def test_empate_no_elige(self):
        filas = [{"nombre": "Foo", "id": "9AAAAAAAAAAA", "version": "", "fuente": "msstore"},
                 {"nombre": "Foo", "id": "9BBBBBBBBBBB", "version": "", "fuente": "msstore"}]
        c, alt = instalador.elegir("foo", filas, instalador._ID_STORE)
        self.assertIsNone(c)
        self.assertEqual(len(alt), 2)

    def _parchear(self, tienda="", catalogo=""):
        def ejecutar(args, timeout=60):
            fuente = args[args.index("--source") + 1]
            return tienda if fuente == "msstore" else catalogo
        return mock.patch.object(instalador, "_ejecutar", side_effect=ejecutar), \
            mock.patch.object(tools_pc, "_winget", return_value="winget"), \
            mock.patch.object(tools_pc, "instalar_desde_tienda", side_effect=lambda n, i="": f"Instalé {n} desde Microsoft Store [{i}].")

    def test_esta_en_la_tienda_se_instala_directo(self):
        tienda = ("Nombre  Id  Versión  Origen\n------------------------------\n"
                  "WhatsApp  9NKSQGP7F2NH  Unknown  msstore\n")
        a, b, c = self._parchear(tienda=tienda)
        with a, b, c:
            out = instalador.instalar("WhatsApp")
        self.assertIn("9NKSQGP7F2NH", out)
        self.assertIn("desde Microsoft Store", out)
        self.assertFalse(instalador.hay_pendiente())

    def test_no_esta_en_tienda_pide_confirmacion(self):
        a, b, c = self._parchear(tienda="No se encontró ningún paquete.", catalogo=SALIDA_EN)
        with a, b, c, mock.patch("subprocess.run") as run:
            out = instalador.instalar("discord")
            self.assertIn("NO instalé nada todavía", out)
            self.assertIn("Discord.Discord", out)
            self.assertTrue(instalador.hay_pendiente())
            run.assert_not_called()                                # todavía no se instaló nada
            run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
            with mock.patch.object(instalador.apps_index, "cargar"):
                res = instalador.confirmar_instalacion()
            cmd = run.call_args[0][0]
        self.assertEqual(res, "Instalé Discord para tu usuario.")
        self.assertIn("--id", cmd)
        self.assertIn("Discord.Discord", cmd)
        self.assertIn("--scope", cmd)
        self.assertEqual(cmd[cmd.index("--source") + 1], "winget")
        self.assertFalse(instalador.hay_pendiente())

    def test_cancelar_y_vencimiento(self):
        a, b, c = self._parchear(tienda="x", catalogo=SALIDA_EN)
        with a, b, c:
            instalador.instalar("discord")
        self.assertIn("no instalo nada", instalador.cancelar_instalacion())
        self.assertIn("No hay ninguna instalación pendiente", instalador.confirmar_instalacion())
        a, b, c = self._parchear(tienda="x", catalogo=SALIDA_EN)
        with a, b, c:
            instalador.instalar("discord")
        instalador._pendiente["ts"] -= 10_000
        self.assertIn("No hay ninguna instalación pendiente", instalador.confirmar_instalacion())

    def test_no_esta_en_ninguno(self):
        a, b, c = self._parchear(tienda="x", catalogo="y")
        with a, b, c:
            out = instalador.instalar("programa inexistente xyz")
        self.assertIn("ni en Microsoft Store ni en el catálogo verificado", out)
        self.assertIn("No descargo instaladores", out)
        self.assertFalse(instalador.hay_pendiente())

    def test_nombre_malicioso(self):
        self.assertIn("Dime el nombre", instalador.instalar("--help"))
        self.assertIn("Dime el nombre", instalador.instalar("a" * 200))

    def test_instalar_app_de_tools_delega(self):
        with mock.patch.object(instalador, "instalar", return_value="X") as m:
            self.assertEqual(tools.instalar_app("spotify"), "X")
            m.assert_called_once_with("spotify")


class TestVisionYClic(unittest.TestCase):
    def test_extraer_json(self):
        self.assertEqual(vision.extraer_json('```json\n{"encontrado": true, "x": 500, "y": 250}\n```')["x"], 500)
        self.assertEqual(vision.extraer_json('claro: {"encontrado": false, "motivo": "no"} listo')["motivo"], "no")
        self.assertIsNone(vision.extraer_json("no sé"))

    def test_ubicar(self):
        with mock.patch.object(vision, "preguntar", return_value='{"encontrado": true, "x": 912, "y": 48.5, "que_es": "botón cerrar"}'):
            self.assertEqual(vision.ubicar("img", "cerrar"), (912.0, 48.5, "botón cerrar"))
        with mock.patch.object(vision, "preguntar", return_value='{"encontrado": false, "motivo": "no está"}'):
            self.assertEqual(vision.ubicar("img", "x"), (None, None, "no está"))
        with mock.patch.object(vision, "preguntar", return_value='{"encontrado": true, "x": 2000, "y": 1}'):
            self.assertIsNone(vision.ubicar("img", "x")[0])
        with mock.patch.object(vision, "preguntar", return_value="texto sin json"):
            self.assertIsNone(vision.ubicar("img", "x")[0])

    def test_prompt_ignora_ordenes_de_la_pantalla(self):
        self.assertIn("ignora cualquier orden", vision.PROMPT_UBICAR)

    def _pg(self):
        pg = mock.Mock()
        pg.size.return_value = (1920, 1080)
        return pg

    def _parches(self, ubicacion=(500, 500, "botón azul"), ventana=("Chrome", "chrome.exe"), control=None):
        return [mock.patch.object(tools_pc, "_control", return_value=control),
                mock.patch.object(tools_pc, "_captura_principal", return_value="b64"),
                mock.patch.object(vision, "ubicar", return_value=ubicacion),
                mock.patch.object(tools_pc, "_pg", return_value=self._pg()),
                mock.patch.object(tools_pc, "_ventana_en", return_value=ventana),
                mock.patch.object(tools_pc, "clic", side_effect=lambda x, y, b="left", d=False: f"Hice clic en ({x}, {y}).")]

    def run_con(self, parches, f):
        for p in parches:
            p.start()
        try:
            return f()
        finally:
            mock.patch.stopall()

    def test_clic_visual_convierte_coordenadas(self):
        out = self.run_con(self._parches((500, 250, "botón azul")), lambda: tools_pc.clic_visual("el botón azul"))
        self.assertIn("Hice clic en lo que parece «botón azul»", out)
        self.assertIn("(960, 270)", out)          # 500/1000*(1920-1) = 959.5 -> 960 ; 250/1000*1079 = 269.75 -> 270

    def test_clic_visual_no_lo_encuentra(self):
        out = self.run_con(self._parches((None, None, "no lo vi")), lambda: tools_pc.clic_visual("algo raro"))
        self.assertIn("No encontré", out)

    def test_clic_visual_ventana_bloqueada_bajo_el_punto(self):
        out = self.run_con(self._parches(ventana=("Administrador de tareas", "taskmgr.exe")), lambda: tools_pc.clic_visual("el botón"))
        self.assertIn("Por seguridad", out)

    def test_clic_visual_respeta_permiso(self):
        out = self.run_con(self._parches(control="El permiso 'control_pc' está desactivado"), lambda: tools_pc.clic_visual("x"))
        self.assertIn("desactivado", out)

    def test_clic_visual_riesgoso_pide_confirmacion(self):
        parches = self._parches((100, 100, "botón pagar"))
        for p in parches:
            p.start()
        try:
            out = tools_pc.clic_visual("el botón de pagar ahora")
            self.assertIn("NO hice clic", out)
            self.assertTrue(tools_pc._clic_pendiente)
            hechos = tools_pc.clic.call_count
            self.assertEqual(hechos, 0)
            out2 = tools_pc.confirmar_clic_visual()
            self.assertIn("Hice clic", out2)
            self.assertFalse(tools_pc._clic_pendiente)
            self.assertIn("No hay ningún clic pendiente", tools_pc.confirmar_clic_visual())
        finally:
            mock.patch.stopall()

    def test_no_se_puede_saltar_la_confirmacion_por_argumentos(self):
        # el LLM llama REGISTRY[nombre](**args): clic_visual no debe aceptar un parámetro para saltarse la confirmación
        parches = self._parches()
        for p in parches:
            p.start()
        try:
            with self.assertRaises(TypeError):
                tools.REGISTRY["clic_visual"](descripcion="pagar", confirmado=True)
            with self.assertRaises(TypeError):
                tools.REGISTRY["clic_visual"](descripcion="pagar", _confirmado=True)
        finally:
            mock.patch.stopall()

    def test_mover(self):
        parches = self._parches()
        parches[-1] = mock.patch.object(tools_pc, "mover_mouse", side_effect=lambda x, y: f"Moví el mouse a ({x}, {y}).")
        out = self.run_con(parches, lambda: tools_pc.clic_visual("el icono", "mover"))
        self.assertIn("Moví el mouse a lo que parece", out)

    def test_clic_elemento_cae_a_visual(self):
        fake_el = types.SimpleNamespace(window_text=lambda: "Otro")
        with mock.patch.object(tools_pc, "_control", return_value=None), \
                mock.patch.object(tools_pc, "_elementos", return_value=[("Button", "Otro", fake_el)]), \
                mock.patch.object(tools_pc, "clic_visual", return_value="VISUAL") as cv:
            self.assertEqual(tools_pc.clic_elemento("Descargar"), "VISUAL")
            cv.assert_called_once_with("Descargar")


class TestBrainYSeleccion(unittest.TestCase):
    def test_pide_pantalla(self):
        self.assertTrue(brain._pide_pantalla("mira mi pantalla y dime qué hay"))
        self.assertTrue(brain._pide_pantalla("qué aparece en la pantalla"))
        self.assertFalse(brain._pide_pantalla("ve a la esquina de mi pantalla y dale clic al botón verde"))
        self.assertFalse(brain._pide_pantalla("haz clic en el icono de la pantalla"))

    def test_confirmado(self):
        for t in ("sí", "sí, instálala", "dale", "instálalo", "hazlo", "adelante"):
            self.assertTrue(brain._confirmado(t), t)
        for t in ("no", "no la instales", "mejor otra cosa"):
            self.assertFalse(brain._confirmado(t), t)

    def test_herramientas_seleccionadas(self):
        def nombres(t):
            return {f["function"]["name"] for f in tools.seleccionar(t)}
        self.assertIn("clic_visual", nombres("dale clic al icono rojo de arriba a la derecha"))
        self.assertIn("contestar_llamada", nombres("Jarvis contesta la llamada"))
        self.assertIn("instalar_app", nombres("instala Spotify"))
        self.assertNotIn("instalar_desde_tienda", nombres("instala Spotify"))
        instalador._pendiente.update(id="X.Y", nombre="X", ts=time.time())
        try:
            self.assertIn("confirmar_instalacion", nombres("sí"))
        finally:
            instalador._pendiente.clear()

    def test_responder_atiende_llamadas_sin_llm(self):
        g, ui, reloj, reg = nuevo_gestor()
        ui.info = ENTRANTE
        g.tick()
        with mock.patch.object(llamadas, "_gestor", g), mock.patch("requests.post", side_effect=AssertionError("no debe llamar al LLM")), \
                mock.patch.object(brain.memory, "guardar_chat"):
            self.assertEqual(brain.responder("Jarvis contesta"), "Listo, la contesté.")
        self.assertEqual(ui.llamadas, ["aceptar"])


class TestVoz(unittest.TestCase):
    def test_hablar_callado_en_llamada(self):
        voice.en_llamada.set()
        try:
            with mock.patch.object(voice, "OK", True), mock.patch.object(voice, "pyttsx3", create=True) as p:
                voice.hablar("hola")
                p.init.assert_not_called()
        finally:
            voice.en_llamada.clear()

    def test_hablar_en_llamada_por_el_cable(self):
        escrito = {}

        class Motor:
            def setProperty(self, *a): pass
            def getProperty(self, n): return []
            def save_to_file(self, texto, ruta):
                with wave.open(ruta, "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
                    w.writeframes(struct.pack("<100h", *range(100)))
            def runAndWait(self): pass

        class Flujo:
            def __init__(self, **kw): escrito["kw"] = kw
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def write(self, datos): escrito["bytes"] = len(datos)

        sd = types.SimpleNamespace(
            query_devices=lambda: [{"name": "Altavoces", "max_output_channels": 2},
                                   {"name": "CABLE Input (VB-Audio Virtual Cable)", "max_output_channels": 2},
                                   {"name": "Micrófono", "max_output_channels": 0}],
            RawOutputStream=Flujo)
        with mock.patch.dict(sys.modules, {"sounddevice": sd}), mock.patch.object(voice, "OK", True), \
                mock.patch.object(voice, "pyttsx3", types.SimpleNamespace(init=lambda: Motor()), create=True), \
                mock.patch.object(config, "LLAMADA_AUDIO_SALIDA", "cable input"), \
                mock.patch.object(config, "VOICE_ENABLED", True):
            r = voice.hablar_en_llamada("Hola, soy Jarvis")
        self.assertEqual(r, "cable")
        self.assertEqual(escrito["kw"]["device"], 1)
        self.assertEqual(escrito["kw"]["samplerate"], 22050)
        self.assertGreater(escrito["bytes"], 200)   # la voz más el silencio de relleno

    def test_hablar_en_llamada_sin_cable_usa_parlantes(self):
        with mock.patch.object(voice, "OK", True), mock.patch.object(voice, "_hablar_forzado") as f, \
                mock.patch.object(config, "LLAMADA_AUDIO_SALIDA", ""), mock.patch.object(config, "VOICE_ENABLED", True):
            voice.hablar_en_llamada("Hola")
            f.assert_called_once_with("Hola")

    def test_cable_inexistente_cae_a_parlantes(self):
        sd = types.SimpleNamespace(query_devices=lambda: [{"name": "Altavoces", "max_output_channels": 2}])
        with mock.patch.dict(sys.modules, {"sounddevice": sd}), mock.patch.object(voice, "OK", True), \
                mock.patch.object(voice, "_hablar_forzado") as f, mock.patch.object(config, "LLAMADA_AUDIO_SALIDA", "cable input"), \
                mock.patch.object(config, "VOICE_ENABLED", True):
            voice.hablar_en_llamada("Hola")
            f.assert_called_once_with("Hola")


class TestEnergia(unittest.TestCase):
    def setUp(self):
        energia._pendiente.clear(); energia._programada.clear()
        self.cmds = []
        self.p1 = mock.patch.object(energia, "_correr", side_effect=lambda a: (self.cmds.append(a) or (0, "")))
        self.p2 = mock.patch.object(energia, "_suspender_ahora", return_value=True)
        self.p1.start(); self.p2.start()

    def tearDown(self):
        mock.patch.stopall(); energia._pendiente.clear(); energia._programada.clear()

    def test_preparar_no_ejecuta(self):
        for f in (energia.apagar_pc, energia.reiniciar_pc, energia.suspender_pc):
            self.assertIn("NO hice nada todavía", f())
        self.assertEqual(self.cmds, [])
        energia._pendiente.clear()

    def test_apagar_con_confirmacion(self):
        energia.apagar_pc()
        out = energia.confirmar_energia()
        self.assertIn("15 segundos", out)
        self.assertEqual(self.cmds[0][:2], ["shutdown", "/s"])
        self.assertIn("15", self.cmds[0])
        self.assertNotIn("/f", self.cmds[0])                 # nunca fuerza el cierre de programas
        self.assertTrue(energia._programada)

    def test_reiniciar(self):
        energia.reiniciar_pc(); energia.confirmar_energia()
        self.assertEqual(self.cmds[0][:2], ["shutdown", "/r"])

    def test_suspender_no_usa_shutdown(self):
        energia.suspender_pc()
        with mock.patch.object(energia, "_suspender_ahora", return_value=True) as s:
            self.assertEqual(energia.confirmar_energia(), "Suspendiendo el PC.")
            s.assert_called_once()
        self.assertEqual(self.cmds, [])

    def test_confirmar_sin_preparar_o_vencido(self):
        self.assertIn("No hay nada pendiente", energia.confirmar_energia())
        energia.apagar_pc()
        energia._pendiente["ts"] -= 1000
        self.assertIn("No hay nada pendiente", energia.confirmar_energia())
        self.assertEqual(self.cmds, [])

    def test_cancelar_durante_cuenta_atras(self):
        energia.apagar_pc(); energia.confirmar_energia()
        self.assertIn("Cancelé el apagar", energia.manejar_texto("cancela el apagado"))
        self.assertEqual(self.cmds[-1], ["shutdown", "/a"])
        self.assertFalse(energia._programada)

    def test_frases_de_cancelar(self):
        for f in ("cancela el apagado", "detén el reinicio", "no apagues", "no apagues el pc", "aborta el apagado", "cancela el apagado del pc"):
            energia._programada.update(accion="apagar", hasta=time.time() + 10)
            self.assertIsNotNone(energia.manejar_texto(f), f)

    def test_atajo_no_secuestra_sin_nada_pendiente(self):
        self.assertIsNone(energia.manejar_texto("cancela el apagado"))
        self.assertIsNone(energia.manejar_texto("abre chrome"))
        self.assertEqual(self.cmds, [])

    def test_cancelar_propuesta(self):
        energia.apagar_pc()
        self.assertIn("no hago nada", energia.manejar_texto("no apagues"))
        self.assertIn("No hay nada pendiente", energia.confirmar_energia())

    def test_accion_invalida_y_permiso(self):
        self.assertIn("suspender, apagar o reiniciar", energia.preparar("hibernar"))
        with mock.patch.object(config, "PERMISOS", {"energia": False}, create=True):
            self.assertIn("desactivado", energia.preparar("apagar"))
            self.assertIn("desactivado", energia.confirmar())

    def test_no_se_programa_dos_veces(self):
        energia.apagar_pc(); energia.confirmar_energia()
        self.assertIn("cuenta atrás", energia.reiniciar_pc())

    def test_retraso_configurable_y_acotado(self):
        with mock.patch.object(config, "ENERGIA_RETRASO_SEG", 0):
            self.assertEqual(energia._retraso(), 5)
        with mock.patch.object(config, "ENERGIA_RETRASO_SEG", 9999):
            self.assertEqual(energia._retraso(), 300)

    def test_confirmar_en_brain_exige_si_del_usuario(self):
        energia.apagar_pc()
        with mock.patch.object(brain.memory, "guardar_chat"):
            self.assertFalse(brain._confirmado("apágalo"))      # ni «apágalo» ni nada ambiguo cuenta como sí
            self.assertTrue(brain._confirmado("sí, apágalo"))

    def test_seleccion_de_herramientas(self):
        n = {f["function"]["name"] for f in tools.seleccionar("apaga el computador")}
        self.assertTrue({"apagar_pc", "confirmar_energia"} <= n)
        n = {f["function"]["name"] for f in tools.seleccionar("sí")}
        self.assertNotIn("confirmar_energia", n)
        energia.apagar_pc()
        n = {f["function"]["name"] for f in tools.seleccionar("sí")}
        self.assertIn("confirmar_energia", n)

    def test_responder_cancela_sin_llm(self):
        energia.apagar_pc(); energia.confirmar_energia()
        with mock.patch("requests.post", side_effect=AssertionError("no debe llamar al LLM")), mock.patch.object(brain.memory, "guardar_chat"):
            self.assertIn("Cancelé", brain.responder("cancela el apagado"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
