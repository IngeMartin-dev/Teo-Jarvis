"""Una conversación de texto con el modelo, SIN herramientas (la usa la conversación de las llamadas).

Usa el proveedor elegido al iniciar Jarvis y, si falla, prueba los demás que tengan clave. Nada de lo que se diga acá
puede ejecutar acciones en el PC: no se envían herramientas al modelo.
"""
import re
import requests
import config

_ORDEN = ("openrouter", "gemini", "groq", "mistral", "cloudflare", "local")


def _limpiar(texto: str) -> str:
    return re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S).strip()


def _openai(url: str, clave: str, modelo: str, mensajes: list, timeout: float, razonamiento: bool = False,
            cabeceras: dict = None):
    payload = {"model": modelo, "messages": mensajes, "temperature": 0.4, "max_tokens": 400}
    if razonamiento:
        payload["reasoning_effort"] = "low"
    cab = {"Authorization": f"Bearer {clave}", **(cabeceras or {})}
    r = requests.post(url, headers=cab, json=payload, timeout=timeout)
    if r.status_code == 400 and razonamiento and "reasoning_effort" in r.text:
        payload.pop("reasoning_effort")
        r = requests.post(url, headers=cab, json=payload, timeout=timeout)
    return r


def _consultar(proveedor: str, mensajes: list, timeout: float):
    """Texto de la respuesta, o None si este proveedor no pudo (sin clave, 429, error...)."""
    if proveedor == "local":
        r = requests.post(config.OLLAMA_URL, timeout=max(timeout, 60), json={
            "model": config.MODEL, "stream": False, "think": False, "options": {"temperature": 0.4},
            "messages": mensajes})
        if r.status_code == 400 and "think" in r.text.lower():
            r = requests.post(config.OLLAMA_URL, timeout=max(timeout, 60), json={
                "model": config.MODEL, "stream": False, "options": {"temperature": 0.4}, "messages": mensajes})
        return _limpiar(r.json()["message"]["content"]) if r.status_code == 200 else None
    r = None
    if proveedor == "gemini" and config.GEMINI_API_KEY:
        r = _openai("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    config.GEMINI_API_KEY, config.GEMINI_MODEL, mensajes, timeout, razonamiento=True)
    elif proveedor == "openrouter" and config.OPENROUTER_API_KEY:
        r = _openai("https://openrouter.ai/api/v1/chat/completions", config.OPENROUTER_API_KEY,
                    config.OPENROUTER_MODEL, mensajes, timeout, cabeceras={"X-Title": "Jarvis"})
    elif proveedor == "mistral" and config.MISTRAL_API_KEY:
        r = _openai("https://api.mistral.ai/v1/chat/completions", config.MISTRAL_API_KEY, config.MISTRAL_MODEL,
                    mensajes, timeout)
    elif proveedor == "cloudflare" and config.CLOUDFLARE_ACCOUNT_ID and config.CLOUDFLARE_API_TOKEN:
        r = _openai(f"https://api.cloudflare.com/client/v4/accounts/{config.CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions",
                    config.CLOUDFLARE_API_TOKEN, config.CLOUDFLARE_MODEL, mensajes, timeout)
    elif proveedor == "groq" and config.GROQ_API_KEY:
        for modelo in list(getattr(config, "GROQ_MODELS", None) or [config.GROQ_MODEL]):
            r = _openai("https://api.groq.com/openai/v1/chat/completions", config.GROQ_API_KEY, modelo, mensajes,
                        timeout, razonamiento=("gpt-oss" in modelo or "qwen" in modelo))
            if r.status_code != 429:   # con 429 se prueba el siguiente modelo
                break
    if r is None or r.status_code != 200:
        return None
    return _limpiar(r.json()["choices"][0]["message"].get("content") or "")


def charlar(sistema: str, mensajes: list, timeout: float = 25.0) -> str:
    """Respuesta del modelo a `mensajes` ([{role, content}]) con la instrucción `sistema`.
    Lanza RuntimeError si ningún proveedor respondió."""
    msgs = [{"role": "system", "content": sistema}] + list(mensajes)
    actual = getattr(config, "PROVEEDOR_ACTUAL", "local")
    orden = [actual] + [p for p in _ORDEN if p != actual]
    for proveedor in orden:
        try:
            texto = _consultar(proveedor, msgs, timeout)
        except (requests.RequestException, KeyError, ValueError, IndexError):
            texto = None
        if texto:
            return texto
    raise RuntimeError("Ningún modelo respondió.")
