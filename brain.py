"""Cerebro: habla con Ollama y ejecuta herramientas."""
import json, requests
import config, memory, tools

SISTEMA = (
    "Eres Jarvis, el asistente personal del usuario en su PC con Windows. Responde siempre en español, "
    "breve y directo. Cuando el usuario pida una acción (abrir apps, crear proyectos, documentos, "
    "agendar, recordar), usa las herramientas. No inventes resultados: informa lo que devuelve la herramienta."
)


def _mensajes(texto: str) -> list[dict]:
    recuerdos = memory.hechos()
    sistema = SISTEMA + (("\nLo que sabes del usuario:\n- " + "\n- ".join(recuerdos)) if recuerdos else "")
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
        for _ in range(5):  # máximo 5 rondas de herramientas
            r = requests.post(config.OLLAMA_URL, json={
                "model": config.MODEL, "messages": msgs, "tools": tools.TOOLS_SPEC, "stream": False,
            }, timeout=180)
            r.raise_for_status()
            m = r.json()["message"]
            msgs.append(m)
            llamadas = m.get("tool_calls")
            if not llamadas:
                out = m.get("content", "").strip() or "Listo."
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
    except Exception as e:
        out = f"Error: {e}"
    memory.guardar_chat("user", texto); memory.guardar_chat("assistant", out)
    return out
