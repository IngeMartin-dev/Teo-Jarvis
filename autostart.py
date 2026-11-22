"""Activa o desactiva que Jarvis arranque con Windows.
Uso:  python autostart.py on   |   python autostart.py off
"""
import sys, winreg
from pathlib import Path

NOMBRE = "Jarvis"
RUTA = r"Software\Microsoft\Windows\CurrentVersion\Run"
pyw = Path(sys.executable).with_name("pythonw.exe")  # sin ventana de consola
main = Path(__file__).with_name("main.py")

if len(sys.argv) < 2 or sys.argv[1] not in ("on", "off"):
    sys.exit("Uso: python autostart.py on|off")

with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUTA, 0, winreg.KEY_SET_VALUE) as k:
    if sys.argv[1] == "on":
        winreg.SetValueEx(k, NOMBRE, 0, winreg.REG_SZ, f'"{pyw}" "{main}"')
        print("Jarvis arrancará con Windows.")
    else:
        try:
            winreg.DeleteValue(k, NOMBRE)
        except FileNotFoundError:
            pass
        print("Autoinicio desactivado.")
