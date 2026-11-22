"""Jarvis: icono en la bandeja del sistema + ventana de chat + voz."""
import threading, tkinter as tk
from tkinter import scrolledtext
import pystray
from PIL import Image, ImageDraw

import brain, voice

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


def procesar(texto: str):
    escribir("Tú", texto)
    def _run():
        out = brain.responder(texto)
        escribir("Jarvis", out)
        voice.hablar(out)
    threading.Thread(target=_run, daemon=True).start()


def al_enviar(_=None):
    t = entrada.get().strip()
    if t:
        entrada.delete(0, "end"); procesar(t)


entrada.bind("<Return>", al_enviar)
root.protocol("WM_DELETE_WINDOW", root.withdraw)


def mostrar():
    root.after(0, lambda: (root.deiconify(), root.lift(), entrada.focus_set()))


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
threading.Thread(target=tray.run, daemon=True).start()
threading.Thread(target=voice.escuchar_en_bucle, args=(procesar, lambda: activo), daemon=True).start()

escribir("Jarvis", "Listo. Escríbeme o di «Hola Jarvis».")
root.mainloop()
