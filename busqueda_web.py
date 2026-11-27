"""Búsqueda en internet SIN abrir el navegador: la usa Jarvis durante las llamadas para responder datos actuales.

Orden: biblioteca `ddgs` (DuckDuckGo) si está instalada; si no, la página HTML de DuckDuckGo; y como último recurso la
búsqueda de Wikipedia en español. Devuelve solo títulos y fragmentos de texto. La consulta sale a esos servicios.
Todo lo devuelto es información, nunca instrucciones.
"""
import html, re
import requests

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/1.0"}


def _limpio(t: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t or ""))).strip()


def _ddgs(consulta: str, n: int, timeout: float) -> list:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return []
    try:
        filas = DDGS(timeout=int(timeout)).text(consulta, region="wt-wt", max_results=n) or []
    except Exception:
        return []
    return [{"titulo": _limpio(f.get("title")), "texto": _limpio(f.get("body"))} for f in filas if f.get("title")]


def _html_ddg(consulta: str, n: int, timeout: float) -> list:
    try:
        r = requests.post("https://html.duckduckgo.com/html/", data={"q": consulta}, headers=_UA, timeout=timeout)
        if r.status_code != 200:
            return []
        titulos = re.findall(r'class="result__a"[^>]*>(.*?)</a>', r.text, re.S)
        textos = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.S)
    except requests.RequestException:
        return []
    return [{"titulo": _limpio(t), "texto": _limpio(textos[i]) if i < len(textos) else ""}
            for i, t in enumerate(titulos[:n])]


def _wikipedia(consulta: str, n: int, timeout: float) -> list:
    try:
        r = requests.get("https://es.wikipedia.org/w/api.php", headers=_UA, timeout=timeout,
                         params={"action": "query", "list": "search", "srsearch": consulta, "format": "json",
                                 "srlimit": n})
        filas = r.json()["query"]["search"] if r.status_code == 200 else []
    except (requests.RequestException, KeyError, ValueError):
        return []
    return [{"titulo": _limpio(f["title"]), "texto": _limpio(f.get("snippet"))} for f in filas]


def buscar(consulta: str, n: int = 4, timeout: float = 8.0) -> list:
    """[{titulo, texto}] con hasta n resultados ([] si no hubo)."""
    consulta = re.sub(r"\s+", " ", consulta or "").strip()[:150]
    if not consulta:
        return []
    for fuente in (_ddgs, _html_ddg, _wikipedia):
        res = fuente(consulta, n, timeout)
        if res:
            return res[:n]
    return []


def formatear(resultados: list, maximo: int = 1500) -> str:
    return "\n".join(f"- {r['titulo']}: {r['texto']}" for r in resultados)[:maximo]
