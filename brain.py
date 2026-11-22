"""Cerebro: habla con Ollama y ejecuta herramientas."""
import json, re, requests
from datetime import datetime
import config, memory, tools

SISTEMA = (
    "Eres Jarvis, el asistente personal del usuario en su PC con Windows. Responde siempre en español, "
    "MUY breve (1 o 2 frases), porque tus respuestas se leen en voz alta. "
    "Cuando el usuario pida una acción (abrir apps o archivos, crear proyectos, documentos, agendar, recordar), "
    "usa las herramientas y nunca digas que hiciste algo sin haberlo hecho con una herramienta. "
    "Si una herramienta falla o no encuentra algo, prueba otra antes de rendirte: por ejemplo, si no es una app "
    "puede ser un sitio web (abrir_url) o un archivo (abrir_archivo). "
    "Zona horaria: America/Bogota. Para agendar usa fechas ISO 8601 sin zona, por ejemplo 2026-11-22T15:00:00."
)


def _mensajes(texto: str) -> list:
    recuerdos = memory.hechos()
    ahora = datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M")
    sistema = SISTEMA + f"\nFecha y hora actual: {ahora}."
    if recuerdos:
        sistema += "\nLo que sabes del usuario:\n- " + "\n- ".join(recuerdos)
    return [{"role": "system", "content": sistema}, *memory.ultimos(), {"role": "user", "content": texto}]


def responder(texto: str) -> str:
    # Atajo sin LLM: rutinas por frase clave
    bajo = texto.lower()
    for frase in config.ROUTINES:
        if frase in bajo:
            out = tools.ejecutar_rutina(frase)
            memory.guardar_chat("user", texto); memory.guardar_chat("assistant", out)
            return out

    msgs = _mensajes(texto)
    try:
        for _ in range(6):  # máximo 6 rondas de herramientas
            r = requests.post(config.OLLAMA_URL, json={
                "model": config.MODEL, "messages": msgs, "tools": tools.TOOLS_SPEC, "stream": False,
                "keep_alive": "30m", "options": {"num_ctx": 4096},
            }, timeout=300)
            r.raise_for_status()
            m = r.json()["message"]
            msgs.append(m)
            llamadas = m.get("tool_calls")
            if not llamadas:
                out = re.sub(r"<think>.*?</think>", "", m.get("content", ""), flags=re.S).strip() or "Listo."
                break
            for c in llamadas:
                nombre = c["function"]["name"]
                args = c["function"].get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                try:
                    res = tools.REGISTRY[nombre](**args)
                except Exception as e:
                    res = f"Error en {nombre}: {e}"
                msgs.append({"role": "tool", "content": str(res)})
        else:
            out = "Me quedé sin pasos para completar eso."
    except requests.ConnectionError:
        out = "No puedo conectar con Ollama. ¿Está abierto? Ejecuta 'ollama serve'."
    except requests.HTTPError as e:
        out = f"Ollama respondió con error ({e.response.status_code}). Revisa que el modelo '{config.MODEL}' exista con 'ollama list'."
    except Exception as e:
        out = f"Error: {e}"
    memory.guardar_chat("user", texto); memory.guardar_chat("assistant", out)
    return out
