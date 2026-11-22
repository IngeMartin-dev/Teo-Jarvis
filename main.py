"""Jarvis: icono en la bandeja + ventana de chat + orbe animado sobre la barra de Windows + voz."""
import ctypes, math, threading, time, tkinter as tk
from ctypes import wintypes
from tkinter import scrolledtext
import pystray
from PIL import Image, ImageDraw

import brain, voice

try:  # coordenadas correctas en pantallas con escalado
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

activo = True
root = tk.Tk()
root.title("Jarvis")
root.geometry("420x520")
root.configure(bg="#0b1220")
root.withdraw()  # arranca oculto en la bandeja

log = scrolledtext.ScrolledText(root, bg="#0b1220", fg="#7dd3fc", font=("Consolas", 10), wrap="word", state="disabled")
log.pack(fill="both", expand=True, padx=8, pady=(8, 4))
entrada = tk.Entry(root, bg="#111a2e", fg="white", insertbackground="white", font=("Consolas", 11))
entrada.pack(fill="x", padx=8, pady=(0, 8), ipady=6)


def escribir(quien: str, texto: str):
    def _w():
        log.config(state="normal"); log.insert("end", f"{quien}: {texto}\n\n"); log.see("end"); log.config(state="disabled")
    root.after(0, _w)


# ---------------- Orbe animado (esquina inferior derecha, sobre la barra de Windows) ----------------
TAM = 120
CLAVE = "#010203"  # color que se vuelve transparente
COLORES = {"escuchando": "#38bdf8", "pensando": "#fbbf24", "hablando": "#34d399"}
estado_actual = {"v": "reposo"}

ov = tk.Toplevel(root)
ov.overrideredirect(True)
ov.attributes("-topmost", True)
ov.attributes("-transparentcolor", CLAVE)
ov.configure(bg=CLAVE)
cv = tk.Canvas(ov, width=TAM, height=TAM, bg=CLAVE, highlightthickness=0)
cv.pack()
ov.withdraw()


def _posicionar():
    r = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0)  # área de trabajo (sin la barra)
    ov.geometry(f"{TAM}x{TAM}+{r.right - TAM - 10}+{r.bottom - TAM - 10}")


def set_estado(e: str):
    def _do():
        estado_actual["v"] = e
        if e == "reposo":
            ov.withdraw()
        elif ov.state() == "withdrawn":
            _posicionar(); ov.deiconify(); ov.attributes("-topmost", True)
    root.after(0, _do)


def animar():
    e = estado_actual["v"]
    if e != "reposo":
        t, c, col = time.time(), TAM / 2, COLORES[e]
        cv.delete("all")
        if e == "escuchando":
            p = (t * 1.1) % 1
            r = 20 + 36 * p
            cv.create_oval(c - r, c - r, c + r, c + r, outline=col, width=2)
        elif e == "pensando":
            a = (t * 270) % 360
            cv.create_arc(c - 36, c - 36, c + 36, c + 36, start=a, extent=100, style="arc", outline=col, width=5)
            cv.create_arc(c - 36, c - 36, c + 36, c + 36, start=a + 180, extent=100, style="arc", outline=col, width=5)
        else:  # hablando
            for i in range(3):
                r = 24 + 9 * i + 6 * math.sin(t * 9 + i * 1.3)
                cv.create_oval(c - r, c - r, c + r, c + r, outline=col, width=3)
        cv.create_oval(c - 16, c - 16, c + 16, c + 16, fill=col, outline="")
        cv.create_oval(c - 7, c - 7, c + 7, c + 7, fill="#e0f2fe", outline="")
    root.after(40, animar)


# ---------------- Lógica ----------------
def procesar(texto: str):
    voice.ocupado.set()  # no escuchar mientras piensa y habla
    escribir("Tú", texto)

    def _run():
        try:
            voice.set_estado("pensando")
            out = brain.responder(texto)
            escribir("Jarvis", out)
            voice.hablar(out)
        finally:
            time.sleep(0.2)
            voice.ocupado.clear()
            voice.set_estado("escuchando" if voice.conversando.is_set() else "reposo")
    threading.Thread(target=_run, daemon=True).start()


def al_enviar(_=None):
    t = entrada.get().strip()
    if t:
        entrada.delete(0, "end"); procesar(t)


entrada.bind("<Return>", al_enviar)
root.protocol("WM_DELETE_WINDOW", root.withdraw)


def mostrar():
    root.after(0, lambda: (root.deiconify(), root.lift(), entrada.focus_set()))


cv.bind("<Button-1>", lambda e: mostrar())


def alternar_voz(icon, item):
    global activo
    activo = not activo


def salir(icon, item):
    icon.stop(); root.after(0, root.destroy)


def icono():
    img = Image.new("RGB", (64, 64), "#0b1220")
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), outline="#38bdf8", width=5)
    d.ellipse((24, 24, 40, 40), fill="#38bdf8")
    return img


menu = pystray.Menu(
    pystray.MenuItem("Abrir Jarvis", lambda i, it: mostrar(), default=True),
    pystray.MenuItem("Escucha por voz", alternar_voz, checked=lambda it: activo),
    pystray.MenuItem("Salir", salir),
)
tray = pystray.Icon("Jarvis", icono(), "Jarvis", menu)

voice.on_estado = set_estado
threading.Thread(target=tray.run, daemon=True).start()
threading.Thread(target=voice.escuchar_en_bucle, args=(procesar, lambda: activo), daemon=True).start()

escribir("Jarvis", "Listo. Escríbeme o di «Hola Jarvis». Después seguiré escuchándote hasta que digas «adiós Jarvis».")
animar()
root.mainloop()
