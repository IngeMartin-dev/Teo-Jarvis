"""Índice de aplicaciones instaladas en Windows + búsqueda difusa por nombre.
Fuentes: menú Inicio, escritorio (accesos .lnk/.url, p. ej. juegos de Steam) y apps de la
Tienda/instaladores (Get-StartApps).
"""
import difflib, json, os, re, subprocess, time, unicodedata
from pathlib import Path
import config

CACHE = config.DATA_DIR / "apps.json"
MAX_EDAD = 12 * 3600  # el índice se reconstruye cada 12 h (o si no encuentra algo)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def _construir() -> dict:
    idx: dict = {}

    def add(nombre, tipo, destino):
        k = _norm(nombre)
        if k and k not in idx:
            idx[k] = [nombre, tipo, destino]

    pd = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    ad = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    pub = Path(os.environ.get("PUBLIC", r"C:\Users\Public"))
    inicio = [pd / "Microsoft/Windows/Start Menu/Programs", ad / "Microsoft/Windows/Start Menu/Programs"]
    escritorios = [Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop", pub / "Desktop"]

    for carpeta, recursivo in [(c, True) for c in inicio] + [(c, False) for c in escritorios]:
        if not carpeta.exists():
            continue
        try:
            for p in (carpeta.rglob("*") if recursivo else carpeta.glob("*")):
                if p.suffix.lower() in (".lnk", ".url"):
                    if any(x in p.stem.lower() for x in ("uninstall", "desinstal")):
                        continue
                    add(p.stem, "archivo", str(p))
        except Exception:
            pass

    # Apps de la Tienda y programas registrados en Inicio
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, timeout=60, creationflags=0x08000000)
        data = json.loads(out.stdout.decode("utf-8", "ignore") or "[]")
        if isinstance(data, dict):
            data = [data]
        for a in data:
            add(a["Name"], "uwp", a["AppID"])
    except Exception:
        pass
    return idx


def cargar(forzar: bool = False) -> dict:
    if not forzar and CACHE.exists() and time.time() - CACHE.stat().st_mtime < MAX_EDAD:
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass
    idx = _construir()
    try:
        CACHE.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return idx


def _puntuar(q: str, idx: dict) -> list:
    qt = set(q.split())
    res = []
    for k, (nombre, tipo, destino) in idx.items():
        kt = set(k.split())
        if q == k:
            s = 1.0
        elif qt and qt <= kt:
            s = 0.9 - 0.01 * len(kt - qt)       # contiene todas las palabras; menos extras = mejor
        elif q in k:
            s = 0.8
        else:
            s = difflib.SequenceMatcher(None, q, k).ratio()
        res.append((s, nombre, tipo, destino))
    res.sort(key=lambda x: -x[0])
    return res


def _lanzar(tipo: str, destino: str):
    if tipo == "archivo":
        os.startfile(destino)
    else:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{destino}"])


def abrir(nombre: str):
    """Devuelve (ok, mensaje)."""
    q = _norm(nombre)
    if not q:
        return False, "No me dijiste qué abrir."
    res = []
    for forzar in (False, True):  # si no está, reconstruye el índice una vez
        res = _puntuar(q, cargar(forzar))
        if res and res[0][0] >= 0.62:
            _, nom, tipo, dest = res[0]
            try:
                _lanzar(tipo, dest)
                return True, f"Abrí {nom}."
            except Exception as e:
                return False, f"Encontré {nom} pero no pude abrirlo: {e}"
    sug = ", ".join(r[1] for r in res[:4])
    return False, f"No encontré una aplicación llamada '{nombre}'." + (f" Parecidas: {sug}." if sug else "")
