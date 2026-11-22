"""Memoria persistente simple (SQLite): hechos + historial de conversación."""
import sqlite3, time
from config import DATA_DIR

_db = sqlite3.connect(DATA_DIR / "memoria.db", check_same_thread=False)
_db.execute("CREATE TABLE IF NOT EXISTS hechos (id INTEGER PRIMARY KEY, texto TEXT, ts REAL)")
_db.execute("CREATE TABLE IF NOT EXISTS chat (id INTEGER PRIMARY KEY, rol TEXT, texto TEXT, ts REAL)")
_db.commit()


def recordar(texto: str) -> str:
    _db.execute("INSERT INTO hechos(texto, ts) VALUES (?, ?)", (texto, time.time()))
    _db.commit()
    return "Guardado en memoria."


def hechos() -> list[str]:
    return [r[0] for r in _db.execute("SELECT texto FROM hechos ORDER BY id")]


def olvidar(fragmento: str) -> str:
    cur = _db.execute("DELETE FROM hechos WHERE texto LIKE ?", (f"%{fragmento}%",))
    _db.commit()
    return f"Olvidé {cur.rowcount} recuerdo(s)."


def guardar_chat(rol: str, texto: str):
    _db.execute("INSERT INTO chat(rol, texto, ts) VALUES (?, ?, ?)", (rol, texto, time.time()))
    _db.commit()


def ultimos(n: int = 12) -> list[dict]:
    filas = _db.execute("SELECT rol, texto FROM chat ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [{"role": r, "content": t} for r, t in reversed(filas)]
