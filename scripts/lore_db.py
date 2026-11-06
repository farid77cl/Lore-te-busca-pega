"""Herramienta de Lore sobre jobs_db.json.

Hace siempre igual las tareas que antes se hacían con scripts sueltos:
heredar notas entre gemelas, sacar las pendientes de calificar, aplicar las
notas, armar el reporte diario y marcar ofertas cerradas.

Decisiones importantes:
  * Una oferta se identifica por su `link` (la misma llave del scraper). Las
    gemelas son las que comparten título y empresa normalizados.
  * Se escribe con CRLF e indentación de 4, como está versionado el archivo,
    y de forma atómica (primero .tmp, luego reemplazo).
  * Una nota de 60 o más sin `aviso_texto` se rechaza: es la regla del aviso.
  * Una oferta se marca `cerrada` solo con evidencia escrita. Un aviso que no
    se pudo abrir o que el scraper dejó de ver no está cerrado: se avisa,
    nada más.

Uso (la base vive en la carpeta de datos: ver config.py):
    python lore_db.py heredar
    python lore_db.py pendientes --out pendientes.json [--lotes 4]
    python lore_db.py aplicar resultados.json [--fecha AAAA-MM-DD]
    python lore_db.py reporte [--fecha AAAA-MM-DD] [--respaldo] [--marcar]
    python lore_db.py cerrar <link> --evidencia "texto"
    python lore_db.py agregar oferta.json [--origen correo]
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

DB = config.JOBS_DB
CAMPOS_NOTA = ("score", "score_detalle", "score_fecha", "aviso_texto")
DIAS_AVISO_VIEJO = 30
DIAS_SIN_VER = 14

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def llave(job):
    """Llave de gemelas: título y empresa normalizados."""
    return (normalizar(job.get("title")), normalizar(job.get("company")))


def cargar(ruta=DB):
    if not Path(ruta).exists():
        return []
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def agregar(jobs, ofertas, hoy, origen=None):
    """Agrega ofertas nuevas (por ejemplo, las de una alerta de correo).

    Salta las que ya están por link. Devuelve cuántas agregó.
    """
    links = {j.get("link") for j in jobs}
    n = 0
    for oferta in ofertas:
        if not oferta.get("link") or oferta["link"] in links:
            continue
        nueva = dict(oferta)
        nueva.setdefault("status", "Alerta del correo" if origen == "correo" else "")
        nueva.setdefault("first_seen", hoy)
        nueva["last_seen"] = hoy
        nueva.setdefault("applied", False)
        if origen:
            nueva["origen"] = origen
        jobs.append(nueva)
        links.add(nueva["link"])
        n += 1
    return n


def guardar(jobs, ruta=DB):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(jobs, ensure_ascii=False, indent=4).replace("\r\n", "\n")
    tmp = Path(ruta).with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(texto)
    tmp.replace(ruta)


def _fecha(texto):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def edad_aviso(job):
    """Días desde la publicación, leídos del campo `status` del portal.

    El texto es relativo al día en que el scraper vio la oferta (`last_seen`).
    Devuelve None si no se puede leer: nunca se adivina.
    """
    texto = normalizar(job.get("status"))
    visto = _fecha(job.get("last_seen")) or _fecha(job.get("first_seen"))
    if not texto or not visto:
        return None
    m = re.search(r"(\d{1,2}) de (\w+)(?: de (\d{4}))?", texto)
    if m and m.group(2) in MESES:
        anio = int(m.group(3)) if m.group(3) else visto.year
        try:
            publicada = date(anio, MESES[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
        if publicada > visto:  # «30 de diciembre» leído en enero
            publicada = publicada.replace(year=anio - 1)
        return (visto - publicada).days
    if "mas de 30 dias" in texto:
        return 31
    if "mas de 15 dias" in texto:
        return 16
    if re.search(r"\b(hoy|horas?|hours?|minutos?|minutes?)\b", texto):
        return 0
    if re.search(r"\b(ayer)\b", texto):
        return 1
    m = re.search(r"(\d+)\s*(dias?|days?|semanas?|weeks?|mes(?:es)?|months?|anos?|years?)", texto)
    if not m:
        return None
    n, unidad = int(m.group(1)), m.group(2)
    if unidad.startswith(("semana", "week")):
        return n * 7
    if unidad.startswith(("mes", "month")):
        return n * 30
    if unidad.startswith(("ano", "year")):
        return n * 365
    return n


def heredar(jobs):
    """Las gemelas sin nota copian la nota (y `reportada`) de una gemela calificada."""
    calificadas = {}
    for job in jobs:
        if job.get("score") is not None:
            calificadas.setdefault(llave(job), job)
    heredadas = 0
    for job in jobs:
        if job.get("score") is not None:
            continue
        origen = calificadas.get(llave(job))
        if not origen:
            continue
        for campo in CAMPOS_NOTA + ("reportada",):
            if campo in origen:
                job[campo] = origen[campo]
        heredadas += 1
    return heredadas


def pendientes(jobs):
    """Ofertas sin nota, una por grupo de gemelas, con los links del grupo."""
    grupos = {}
    for job in jobs:
        if job.get("score") is None:
            grupos.setdefault(llave(job), []).append(job)
    salida = []
    for grupo in grupos.values():
        job = grupo[0]
        salida.append({
            "links": [j["link"] for j in grupo],
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "source": job.get("source"),
            "link": job.get("link"),
            "description": (job.get("description") or "")[:600],
        })
    return salida


def aplicar(jobs, resultados, fecha):
    """Escribe las notas. Cada resultado trae `links` y la nota; sus gemelas la heredan."""
    por_link = {j["link"]: j for j in jobs}
    errores, escritas = [], 0
    for r in resultados:
        if r.get("score", 0) >= 60 and not r.get("aviso_texto"):
            errores.append(f"{r.get('links')}: nota {r['score']} sin aviso_texto")
            continue
        for link in r.get("links", []):
            job = por_link.get(link)
            if job is None:
                errores.append(f"{link}: no está en la base")
                continue
            job["score"] = int(r["score"])
            job["score_detalle"] = r["score_detalle"]
            job["score_fecha"] = r.get("score_fecha", fecha)
            if r.get("aviso_texto"):
                job["aviso_texto"] = r["aviso_texto"]
            escritas += 1
    return escritas, errores


def _alertas(job, hoy):
    alertas = []
    edad = edad_aviso(job)
    if edad is not None and edad > DIAS_AVISO_VIEJO:
        alertas.append(f"aviso de hace {edad} días")
    visto = _fecha(job.get("last_seen"))
    if visto and (hoy - visto).days > DIAS_SIN_VER:
        alertas.append(f"el portal no la muestra desde el {visto.isoformat()}")
    return alertas


def reporte(jobs, hoy, respaldo=False):
    """Ofertas para el reporte: hasta 5 de 75 o más; con `respaldo`, además hasta
    3 de 60 a 74 (sección fija desde el 29/10/2026, haya o no de 75 o más).
    Nunca repite, nunca muestra cerradas ni postuladas.
    """
    vistas, candidatas = set(), []
    ya_mostradas = {llave(j) for j in jobs if j.get("reportada") or j.get("applied")}
    for job in sorted(jobs, key=lambda j: -(j.get("score") or 0)):
        k = llave(job)
        if k in vistas or k in ya_mostradas or job.get("cerrada"):
            continue
        vistas.add(k)
        if (job.get("score") or 0) >= 60:
            candidatas.append(job)
    altas = [j for j in candidatas if j["score"] >= 75][:5]
    medias = [j for j in candidatas if j["score"] < 75][:3] if respaldo else []
    if not medias:
        return altas, "75+"
    if not altas:
        return medias, "60-74"
    return altas + medias, "75+ y 60-74"


def seccion_titulo(jobs, texto, minimo=50, maximo=3):
    """Sección aparte por título (p. ej. «asistente comercial»): hasta `maximo`
    ofertas desde `minimo` puntos que no estén ya reportadas, postuladas ni cerradas.
    No reemplaza al ranking: la persona pidió verlas aunque queden bajo 60.
    """
    buscado = normalizar(texto)
    ya_mostradas = {llave(j) for j in jobs if j.get("reportada") or j.get("applied")}
    vistas, salida = set(), []
    for job in sorted(jobs, key=lambda j: -(j.get("score") or 0)):
        k = llave(job)
        if (buscado not in k[0] or k in vistas or k in ya_mostradas
                or job.get("cerrada") or (job.get("score") or 0) < minimo):
            continue
        vistas.add(k)
        salida.append(job)
        if len(salida) == maximo:
            break
    return salida


def marcar_reportadas(jobs, elegidas, fecha):
    llaves = {llave(j) for j in elegidas}
    for job in jobs:
        if llave(job) in llaves:
            job["reportada"] = fecha


def tramos(jobs, fecha_alta):
    nuevas = [j for j in jobs if j.get("first_seen") == fecha_alta]
    cuenta = {"75+": 0, "60-74": 0, "<60": 0, "sin nota": 0}
    for j in nuevas:
        s = j.get("score")
        if s is None:
            cuenta["sin nota"] += 1
        else:
            cuenta["75+" if s >= 75 else "60-74" if s >= 60 else "<60"] += 1
    return len(nuevas), cuenta


def cerrar(jobs, link, evidencia, fecha):
    if not evidencia.strip():
        raise ValueError("cerrar necesita evidencia escrita")
    for job in jobs:
        if job["link"] == link:
            job["cerrada"] = {"fecha": fecha, "evidencia": evidencia.strip()}
            return True
    return False


def _cli(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Herramienta de Lore sobre jobs_db.json")
    p.add_argument("--db", default=str(DB))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("heredar")
    pe = sub.add_parser("pendientes")
    pe.add_argument("--out", required=True)
    pe.add_argument("--lotes", type=int, default=1)
    ap = sub.add_parser("aplicar")
    ap.add_argument("resultados", nargs="+")
    ap.add_argument("--fecha", default=date.today().isoformat())
    re_ = sub.add_parser("reporte")
    re_.add_argument("--fecha", default=date.today().isoformat())
    re_.add_argument("--respaldo", action="store_true")
    re_.add_argument("--marcar", action="store_true")
    re_.add_argument("--titulo", action="append", default=[],
                     help="sección aparte para un título, p. ej. «asistente comercial» (desde 50 puntos)")
    ce = sub.add_parser("cerrar")
    ce.add_argument("link")
    ce.add_argument("--evidencia", required=True)
    ce.add_argument("--fecha", default=date.today().isoformat())
    ag = sub.add_parser("agregar", help="agrega ofertas desde un JSON (una oferta o una lista)")
    ag.add_argument("archivo")
    ag.add_argument("--origen", default=None)
    ag.add_argument("--fecha", default=date.today().isoformat())
    a = p.parse_args(argv)

    jobs = cargar(a.db)
    if a.cmd == "heredar":
        print(f"heredadas: {heredar(jobs)}")
        guardar(jobs, a.db)
    elif a.cmd == "pendientes":
        filas = pendientes(jobs)
        if a.lotes <= 1:
            Path(a.out).write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            base = Path(a.out)
            for i in range(a.lotes):
                ruta = base.with_name(f"{base.stem}{i}{base.suffix}")
                ruta.write_text(json.dumps(filas[i::a.lotes], ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"pendientes: {len(filas)} grupos")
    elif a.cmd == "aplicar":
        resultados = []
        for ruta in a.resultados:
            resultados += json.loads(Path(ruta).read_text(encoding="utf-8"))
        escritas, errores = aplicar(jobs, resultados, a.fecha)
        heredadas = heredar(jobs)
        guardar(jobs, a.db)
        print(f"notas escritas: {escritas} · heredadas: {heredadas} · errores: {len(errores)}")
        for e in errores:
            print(f"  ERROR {e}")
        sin_nota = sum(1 for j in jobs if j.get("score") is None)
        print(f"sin nota en la base: {sin_nota}")
        if errores:
            sys.exit(1)
    elif a.cmd == "reporte":
        hoy = date.fromisoformat(a.fecha)
        total, cuenta = tramos(jobs, a.fecha)
        print(f"nuevas hoy: {total} · {cuenta}")
        elegidas, tramo = reporte(jobs, hoy, a.respaldo)
        print(f"para mostrar ({tramo}): {len(elegidas)}")
        for j in elegidas:
            d = j.get("score_detalle", {})
            alertas = "; ".join(_alertas(j, hoy))
            print(f"- {j['score']} | {j['title']} | {j['company']} | {j.get('source')} | {j['link']}")
            print(f"    H{d.get('habilidades')} N{d.get('nivel')} S{d.get('sector')} P{d.get('practico')} · {d.get('porque')}")
            if alertas:
                print(f"    ⚠ {alertas}")
        for texto in a.titulo:
            extra = seccion_titulo(jobs, texto)
            extra = [j for j in extra if j not in elegidas]
            print(f"sección «{texto}» (desde 50): {len(extra)}")
            for j in extra:
                d = j.get("score_detalle", {})
                print(f"- {j['score']} | {j['title']} | {j['company']} | {j.get('source')} | {j['link']}")
                print(f"    H{d.get('habilidades')} N{d.get('nivel')} S{d.get('sector')} P{d.get('practico')} · {d.get('porque')}")
            elegidas = elegidas + extra
        if a.marcar and elegidas:
            marcar_reportadas(jobs, elegidas, a.fecha)
            guardar(jobs, a.db)
            print("marcadas como reportadas (con sus gemelas)")
    elif a.cmd == "cerrar":
        if not cerrar(jobs, a.link, a.evidencia, a.fecha):
            print("no está en la base")
            sys.exit(1)
        guardar(jobs, a.db)
        print("cerrada")
    elif a.cmd == "agregar":
        datos = json.loads(Path(a.archivo).read_text(encoding="utf-8"))
        ofertas = datos if isinstance(datos, list) else [datos]
        n = agregar(jobs, ofertas, a.fecha, a.origen)
        guardar(jobs, a.db)
        print(f"agregadas: {n}")


if __name__ == "__main__":
    _cli()
