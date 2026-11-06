"""Scraper de ofertas laborales para Lore (portales de Chile).

Fuentes: Laborum, LinkedIn, Trabajando.cl, CompuTrabajo.cl, Chiletrabajos e Indeed.
Solo se guardan ofertas de la región elegida en ajustes.json (por defecto,
la Región Metropolitana), más las remotas si se aceptan.

Decisiones importantes:
  * Un solo navegador para las seis fuentes, que corren en paralelo.
  * La base de datos NUNCA se sobrescribe con resultados vacios: si las seis
    fuentes fallan (bloqueo, cambio de HTML, sin internet) el archivo queda
    intacto y el proceso sale con codigo 1.
  * El historial es acumulativo: las ofertas de busquedas anteriores se
    conservan. Solo se refrescan los campos de las que vuelven a aparecer.
  * Los logs van a stderr; en modo --url stdout contiene solo el JSON.
"""

import asyncio
import json
import re
import sys
import unicodedata
from pathlib import Path
from datetime import date
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

import config
import regiones

# Región activa. main_scrape la carga desde ajustes.json; las pruebas la cambian.
REGION = regiones.region("metropolitana")
INCLUIR_REMOTO = True


def log(msg):
    """Los mensajes van a stderr para no contaminar la salida JSON."""
    print(msg, file=sys.stderr, flush=True)


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _limpiar(texto, por_defecto):
    """Colapsa espacios y saltos de linea. CompuTrabajo entrega 'Hace  2  dias'."""
    return " ".join((texto or "").split()) or por_defecto


def _job(title, company, location, status, link, description, source):
    """Construye una oferta con todos los campos presentes y saneados."""
    return {
        "title": _limpiar(title, "Sin titulo"),
        "company": _limpiar(company, "Empresa Confidencial"),
        "location": _limpiar(location, "Chile"),
        "status": _limpiar(status, "Reciente"),
        "link": (link or "").strip(),
        "description": (description or "").strip(),
        "source": source,
    }


async def _new_page(browser):
    """Contexto aislado + stealth. Cada fuente usa el suyo."""
    context = await browser.new_context(user_agent=config.USER_AGENT)
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)
    return context, page


# -------------------------------------------------------------------------
# Fuentes
# -------------------------------------------------------------------------

async def scrape_laborum(browser, query, pages=1):
    query_slug = slugify(query)
    jobs, seen = [], set()
    context, page = await _new_page(browser)
    try:
        for p_num in range(1, pages + 1):
            url = (
                f"https://www.laborum.cl/{REGION.get('laborum', '')}"
                f"empleos-busqueda-{query_slug}.html?page={p_num}"
            )
            log(f"[Laborum] p{p_num}: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)
                soup = BeautifulSoup(await page.content(), "html.parser")

                for card in soup.find_all("a", href=re.compile(r".*/empleos/.*")):
                    h2 = card.find("h2")
                    if not h2:
                        continue
                    href = card.get("href") or ""
                    if not href:
                        continue
                    link = "https://www.laborum.cl" + href if href.startswith("/") else href
                    if link in seen:
                        continue

                    h3_tags = card.find_all("h3")
                    p_tag = card.find("p") or card.find(
                        "div", class_=re.compile(r".*Description.*")
                    )
                    seen.add(link)
                    jobs.append(_job(
                        title=h2.get_text(strip=True),
                        company=h3_tags[1].get_text(strip=True) if len(h3_tags) > 1 else None,
                        location=h3_tags[2].get_text(strip=True) if len(h3_tags) > 2 else None,
                        status=h3_tags[0].get_text(strip=True) if h3_tags else None,
                        link=link,
                        description=p_tag.get_text(strip=True) if p_tag else "",
                        source="Laborum",
                    ))
            except Exception as e:
                log(f"[Laborum] error en p{p_num}: {e}")
    finally:
        await context.close()
    log(f"[Laborum] {len(jobs)} ofertas.")
    return jobs


async def scrape_linkedin(browser, query, pages=1):
    jobs, seen = [], set()
    # "Region Metropolitana, Chile" LinkedIn lo resolvia a Tarapaca; en ingles
    # si lo entiende. Igual se filtra despues por la ubicacion.
    location_rm = quote_plus(REGION["linkedin"]).replace("+", "%20")
    context, page = await _new_page(browser)
    try:
        for p_num in range(pages):
            start = p_num * 25
            url = (
                f"https://www.linkedin.com/jobs/search?"
                f"keywords={query.replace(' ', '%20')}&location={location_rm}&start={start}"
            )
            log(f"[LinkedIn] p{p_num + 1}: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)
                soup = BeautifulSoup(await page.content(), "html.parser")

                for card in soup.find_all("div", class_=re.compile(r"base-search-card")):
                    title_tag = card.find("h3", class_=re.compile(r"base-search-card__title"))
                    link_tag = card.find("a", class_=re.compile(r"base-card__full-link"))
                    if not title_tag or not link_tag:
                        continue
                    link = (link_tag.get("href") or "").split("?")[0]
                    # Sin link la oferta es inservible: no se puede abrir ni deduplicar.
                    if not link or link in seen:
                        continue

                    company_tag = card.find(
                        "a", class_=re.compile(r"base-search-card__subtitle")
                    ) or card.find("h4", class_=re.compile(r"base-search-card__subtitle"))
                    location_tag = card.find("span", class_=re.compile(r"job-search-card__location"))
                    status_tag = card.find("time")

                    seen.add(link)
                    jobs.append(_job(
                        title=title_tag.get_text(strip=True),
                        company=company_tag.get_text(strip=True) if company_tag else None,
                        location=location_tag.get_text(strip=True) if location_tag else None,
                        status=status_tag.get_text(strip=True) if status_tag else None,
                        link=link,
                        description="Ver detalles en LinkedIn.",
                        source="LinkedIn",
                    ))
            except Exception as e:
                log(f"[LinkedIn] error en p{p_num + 1}: {e}")
    finally:
        await context.close()
    log(f"[LinkedIn] {len(jobs)} ofertas.")
    return jobs


async def scrape_trabajando(browser, query, pages=1):
    jobs, seen = [], set()
    query_encoded = query.replace(" ", "%20")
    context, page = await _new_page(browser)
    try:
        for p_num in range(1, pages + 1):
            url = f"https://www.trabajando.cl/trabajo-empleo/{query_encoded}?pagina={p_num}"
            log(f"[Trabajando] p{p_num}: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(4000)

                # Scroll para forzar la carga de resultados dinamicos.
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 600)")
                    await page.wait_for_timeout(800)

                soup = BeautifulSoup(await page.content(), "html.parser")
                container = soup.select_one("#listadoOfertas")
                if not container:
                    log(f"[Trabajando] sin contenedor en p{p_num}, corto aqui.")
                    break

                cards = container.find_all("div", recursive=False)
                log(f"[Trabajando] {len(cards)} tarjetas en p{p_num}.")

                for card in cards:
                    title_tag = card.select_one("h2 a")
                    if not title_tag:
                        continue
                    href = title_tag.get("href") or ""
                    if not href:
                        continue
                    link = "https://www.trabajando.cl" + href if href.startswith("/") else href
                    if link in seen:
                        continue

                    # Las tarjetas traen clases propias; los <span> sueltos
                    # empiezan por la fecha y corrian todos los campos.
                    company_tag = card.select_one("span.type")
                    loc_tag = card.select_one("span.location")
                    status_tag = card.select_one("span.date") or card.select_one("time")
                    desc_tag = card.select_one("p.description") or card.select_one("p")

                    seen.add(link)
                    jobs.append(_job(
                        title=title_tag.get_text(strip=True),
                        company=company_tag.get_text(strip=True) if company_tag else None,
                        location=loc_tag.get_text(strip=True) if loc_tag else None,
                        status=status_tag.get_text(strip=True) if status_tag else None,
                        link=link,
                        description=desc_tag.get_text(" ", strip=True) if desc_tag else "",
                        source="Trabajando",
                    ))
            except Exception as e:
                log(f"[Trabajando] error en p{p_num}: {e}")
    finally:
        await context.close()
    log(f"[Trabajando] {len(jobs)} ofertas.")
    return jobs


async def scrape_computrabajo(browser, query, pages=1):
    jobs, seen = [], set()
    # La URL con filtro de region redirige a un slug canonico, pero conserva
    # tanto la busqueda como la paginacion. Verificado: p1 y p2 no se solapan.
    if REGION.get("computrabajo"):
        base = f"https://cl.computrabajo.com/empleos-en-{REGION['computrabajo']}"
    else:
        base = f"https://cl.computrabajo.com/trabajo-de-{slugify(query)}"
    query_encoded = quote_plus(query)
    context, page = await _new_page(browser)
    try:
        for p_num in range(1, pages + 1):
            url = f"{base}?q={query_encoded}&p={p_num}"
            log(f"[CompuTrabajo] p{p_num}: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3500)
                soup = BeautifulSoup(await page.content(), "html.parser")

                cards = soup.select("article.box_offer")
                if not cards:
                    log(f"[CompuTrabajo] sin tarjetas en p{p_num}, corto aqui.")
                    break
                log(f"[CompuTrabajo] {len(cards)} tarjetas en p{p_num}.")

                for card in cards:
                    title_tag = card.select_one("h2 a")
                    if not title_tag:
                        continue
                    href = title_tag.get("href") or ""
                    if not href:
                        continue
                    link = "https://cl.computrabajo.com" + href if href.startswith("/") else href
                    if link in seen:
                        continue

                    company_tag = card.select_one("a.t_ellipsis") or card.select_one("p.dFlex")
                    # El nombre de la empresa tambien lleva las clases fs16/mt5,
                    # asi que hay que excluir el bloque dFlex para la ubicacion.
                    loc_tag = card.select_one("p.fs16.mt5:not(.dFlex)")
                    status_tag = card.select_one("p.fs13.fc_aux")

                    seen.add(link)
                    jobs.append(_job(
                        # El h2 arrastra tags como "Postulado"/"Vista": se usa el <a>.
                        title=title_tag.get_text(strip=True),
                        company=company_tag.get_text(strip=True) if company_tag else None,
                        location=loc_tag.get_text(strip=True) if loc_tag else None,
                        status=status_tag.get_text(" ", strip=True) if status_tag else None,
                        link=link,
                        # El listado no trae resumen; la descripcion vive en el detalle.
                        description="Ver descripcion completa en CompuTrabajo.",
                        source="CompuTrabajo",
                    ))
            except Exception as e:
                log(f"[CompuTrabajo] error en p{p_num}: {e}")
    finally:
        await context.close()
    log(f"[CompuTrabajo] {len(jobs)} ofertas.")
    return jobs


async def scrape_chiletrabajos(browser, query, pages=1):
    jobs, seen = [], set()
    # El parametro 13 es la ciudad; 1022 ("Santiago") cubre toda la Region
    # Metropolitana. La paginacion va en la ruta, de 30 en 30.
    filtros = {"2": query, "f": "2"}
    if REGION.get("chiletrabajos"):
        filtros["13"] = REGION["chiletrabajos"]
    params = urlencode(filtros)
    context, page = await _new_page(browser)
    try:
        for p_num in range(pages):
            offset = f"/{p_num * 30}" if p_num else ""
            url = f"https://www.chiletrabajos.cl/encuentra-un-empleo{offset}?{params}"
            log(f"[Chiletrabajos] p{p_num + 1}: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2500)
                soup = BeautifulSoup(await page.content(), "html.parser")

                cards = soup.select("div.job-item")
                if not cards:
                    log(f"[Chiletrabajos] sin tarjetas en p{p_num + 1}, corto aqui.")
                    break
                log(f"[Chiletrabajos] {len(cards)} tarjetas en p{p_num + 1}.")

                for card in cards:
                    title_tag = card.select_one("h2 a")
                    if not title_tag:
                        continue
                    link = (title_tag.get("href") or "").strip()
                    if not link or link in seen:
                        continue

                    # Primer h3: "Empresa, <a>Ciudad</a>". Segundo h3: la fecha.
                    metas = card.select("h3.meta")
                    company = location = status = None
                    if metas:
                        ciudad = metas[0].find("a")
                        location = ciudad.get_text(strip=True) if ciudad else None
                        if ciudad:
                            ciudad.extract()
                        company = metas[0].get_text(" ", strip=True).rstrip(",")
                    if len(metas) > 1:
                        status = metas[1].get_text(" ", strip=True)
                    desc_tag = card.select_one("p.description")
                    if desc_tag:
                        for boton in desc_tag.select("a.ver-mas-btn"):
                            boton.extract()

                    seen.add(link)
                    jobs.append(_job(
                        title=title_tag.get_text(strip=True),
                        company=company,
                        location=location,
                        status=status,
                        link=link,
                        description=desc_tag.get_text(" ", strip=True) if desc_tag else "",
                        source="Chiletrabajos",
                    ))
            except Exception as e:
                log(f"[Chiletrabajos] error en p{p_num + 1}: {e}")
    finally:
        await context.close()
    log(f"[Chiletrabajos] {len(jobs)} ofertas.")
    return jobs


# Indeed esta detras de Cloudflare: desde un servidor en la nube responde 401
# con "Security Check" / "Un momento" (verificado 13/10/2026). Desde el PC de
# Con internet residencial deberia cargar. Si sale el muro, se registra
# y se devuelve vacio sin tocar a las demas fuentes.
INDEED_BLOQUEO = ("security check", "un momento", "just a moment", "verificacion adicional")


def _parse_indeed(html):
    """Lee las tarjetas del listado de Indeed. Separado para poder probarlo."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for card in soup.select("div.job_seen_beacon, td.resultContent"):
        enlace = card.select_one("h2.jobTitle a[data-jk], a.jcs-JobTitle[data-jk], a[data-jk]")
        if not enlace:
            continue
        jk = enlace.get("data-jk")
        titulo = enlace.select_one("span[title]")
        empresa = card.select_one('[data-testid="company-name"], span.companyName')
        lugar = card.select_one('[data-testid="text-location"], div.companyLocation')
        fecha = card.select_one('[data-testid="myJobsStateDate"], span.date')
        resumen = card.select_one('[data-testid="belowJobSnippet"], div.job-snippet')
        jobs.append(_job(
            title=titulo.get("title") if titulo else enlace.get_text(strip=True),
            company=empresa.get_text(strip=True) if empresa else None,
            location=lugar.get_text(" ", strip=True) if lugar else None,
            status=fecha.get_text(" ", strip=True) if fecha else None,
            link=f"https://cl.indeed.com/viewjob?jk={jk}",
            description=resumen.get_text(" ", strip=True) if resumen else "",
            source="Indeed",
        ))
    return jobs


async def scrape_indeed(browser, query, pages=1):
    jobs, seen = [], set()
    params = {"q": query, "l": REGION["indeed"]}
    context, page = await _new_page(browser)
    try:
        for p_num in range(pages):
            url = "https://cl.indeed.com/jobs?" + urlencode({**params, "start": p_num * 10})
            log(f"[Indeed] p{p_num + 1}: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(4000)
                titulo = slugify(await page.title()).replace("-", " ")
                if any(b in titulo for b in INDEED_BLOQUEO):
                    log("[Indeed] bloqueado por Cloudflare; corre desde tu computador.")
                    break
                tarjetas = [j for j in _parse_indeed(await page.content()) if j["link"] not in seen]
                if not tarjetas:
                    log(f"[Indeed] sin tarjetas en p{p_num + 1}, corto aqui.")
                    break
                log(f"[Indeed] {len(tarjetas)} tarjetas en p{p_num + 1}.")
                for j in tarjetas:
                    seen.add(j["link"])
                    jobs.append(j)
            except Exception as e:
                log(f"[Indeed] error en p{p_num + 1}: {e}")
    finally:
        await context.close()
    log(f"[Indeed] {len(jobs)} ofertas.")
    return jobs


# -------------------------------------------------------------------------
# Sitios extra (definidos por la persona en sitios.json, sin tocar código)
# -------------------------------------------------------------------------

def cargar_sitios_extra(ruta=None):
    """Lee sitios.json de la carpeta de datos. Devuelve solo los activos."""
    ruta = Path(ruta or config.SITIOS)
    if not ruta.exists():
        return []
    try:
        sitios = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"[sitios.json] no se pudo leer ({e}); se ignora.")
        return []
    activos = []
    for s in sitios:
        faltan = [c for c in ("nombre", "url", "tarjeta", "titulo") if not s.get(c)]
        if faltan:
            log(f"[sitios.json] '{s.get('nombre', '?')}' sin {', '.join(faltan)}; se salta.")
            continue
        if s.get("activo", True):
            activos.append(s)
    return activos


def url_sitio(sitio, query, p_num):
    """Arma la URL de búsqueda. p_num parte en 1.

    Marcadores: {query} (codificada para URL), {query_slug} (con guiones),
    {page} (1, 2, 3…) y {offset} ((página - 1) × por_pagina).
    """
    por_pagina = int(sitio.get("por_pagina", 20))
    return sitio["url"].format(
        query=quote_plus(query), query_slug=slugify(query),
        page=p_num, offset=(p_num - 1) * por_pagina,
    )


def _texto(nodo, selector):
    if not selector:
        return None
    hallado = nodo.select_one(selector)
    return hallado.get_text(" ", strip=True) if hallado else None


def parsear_sitio(html, sitio):
    """Extrae ofertas de una página de resultados según los selectores CSS del sitio."""
    soup = BeautifulSoup(html, "html.parser")
    base = sitio.get("base", "")
    jobs, seen = [], set()
    for card in soup.select(sitio["tarjeta"]):
        titulo = card.select_one(sitio["titulo"])
        if not titulo:
            continue
        enlace = card.select_one(sitio["link"]) if sitio.get("link") else None
        if enlace is None:
            enlace = titulo if titulo.name == "a" else (titulo.find("a") or card.find("a"))
        href = (enlace.get("href") if enlace else "") or ""
        if not href:
            continue
        link = base + href if href.startswith("/") else href
        if link in seen:
            continue
        seen.add(link)
        jobs.append(_job(
            title=titulo.get_text(" ", strip=True),
            company=_texto(card, sitio.get("empresa")),
            location=_texto(card, sitio.get("ubicacion")) or sitio.get("ubicacion_fija"),
            status=_texto(card, sitio.get("fecha")),
            link=link,
            description=(_texto(card, sitio.get("descripcion")) or "")[:config.MAX_DESCRIPCION],
            source=sitio["nombre"],
        ))
    return jobs


async def scrape_sitio(browser, query, pages, sitio):
    nombre = sitio["nombre"]
    jobs, seen = [], set()
    context, page = await _new_page(browser)
    try:
        for p_num in range(1, pages + 1):
            url = url_sitio(sitio, query, p_num)
            log(f"[{nombre}] p{p_num}: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(int(sitio.get("espera_ms", 3000)))
                nuevas = [j for j in parsear_sitio(await page.content(), sitio) if j["link"] not in seen]
                if not nuevas:
                    log(f"[{nombre}] sin ofertas en p{p_num}, corto aqui.")
                    break
                seen.update(j["link"] for j in nuevas)
                jobs.extend(nuevas)
            except Exception as e:
                log(f"[{nombre}] error en p{p_num}: {e}")
    finally:
        await context.close()
    log(f"[{nombre}] {len(jobs)} ofertas.")
    return jobs


# -------------------------------------------------------------------------
# Filtro por región
# -------------------------------------------------------------------------

# Sitios de sitios.json que declaran "filtra_region_en_url": true.
_EXTRAS_FILTRADOS_EN_URL = set()


def es_de_la_region(job):
    """True si la oferta es de la región elegida (ver regiones.py).

    LinkedIn ignora a veces el filtro de ubicación, y Trabajando y Chiletrabajos
    no filtran la región de forma confiable, así que se revisa el texto de la
    ubicación contra las comunas. Una ubicación vaga ("Chile") se descarta.
    """
    if job.get("source") in _EXTRAS_FILTRADOS_EN_URL:
        return True
    return regiones.es_de_la_region(job, REGION, INCLUIR_REMOTO)


OFFER_ID_RE = re.compile(r"^[0-9A-F]{32}$", re.I)


def sanear_url(url):
    """Quita los parametros de rastreo que traen los correos de alerta.

    CompuTrabajo REDIRIGE la ficha de la oferta al listado de resultados
    cuando la URL incluye `fgoa`. Con el parametro puesto se extrae la pagina
    equivocada; sin el, la ficha carga normal.
    """
    partes = urlsplit(url)
    query = [
        (k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True)
        if k.lower() != "fgoa" and not k.lower().startswith("utm_")
    ]
    return urlunsplit(
        (partes.scheme, partes.netloc, partes.path, urlencode(query), partes.fragment)
    )


async def _resolver_ficha_computrabajo(page, url):
    """Convierte una URL de listado con el id de la oferta en el fragmento.

    Los correos de alerta de CompuTrabajo enlazan al listado y sennalan la
    oferta con `#<id de 32 hex>`. Aqui se abre ese listado y se busca la
    tarjeta con ese `data-id` para obtener el enlace real de la ficha.
    """
    partes = urlsplit(url)
    if "/ofertas-de-trabajo/" in partes.path or not OFFER_ID_RE.match(partes.fragment):
        return url

    log(f"[URL] es un listado; busco la oferta {partes.fragment} dentro.")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3500)
    soup = BeautifulSoup(await page.content(), "html.parser")
    tarjeta = soup.select_one(f'article[data-id="{partes.fragment}"] h2 a')
    if not tarjeta or not tarjeta.get("href"):
        # Devolver el listado seria peor que fallar: se guardaria una tarjeta
        # con el titulo del buscador en vez de la oferta.
        log("[URL] la oferta no aparece en ese listado (pudo expirar o quedar en otra pagina).")
        return None
    href = tarjeta["href"]
    ficha = "https://cl.computrabajo.com" + href if href.startswith("/") else href
    log(f"[URL] ficha resuelta: {ficha}")
    return ficha


def _fuente_de(url):
    """Nombre de la fuente segun el dominio."""
    if "linkedin.com" in url:
        return "LinkedIn"
    if "trabajando.cl" in url:
        return "Trabajando"
    if "computrabajo.com" in url:
        return "CompuTrabajo"
    if "chiletrabajos.cl" in url:
        return "Chiletrabajos"
    if "indeed.com" in url:
        return "Indeed"
    if "laborum.cl" in url:
        return "Laborum"
    for sitio in cargar_sitios_extra():
        dominio = urlsplit(sitio["url"]).netloc.removeprefix("www.")
        if dominio and dominio in url:
            return sitio["nombre"]
    return urlsplit(url).netloc.removeprefix("www.") or "Otro"


def _html_a_texto(fragmento):
    """El campo description del JSON-LD viene con etiquetas HTML dentro."""
    return BeautifulSoup(fragmento or "", "html.parser").get_text(" ", strip=True)


def _extraer_json_ld(soup):
    """Lee los datos estructurados schema.org/JobPosting de la pagina.

    Es mucho mas estable que los selectores CSS: es lo que los portales
    publican para Google, con los campos ya separados y sin migas de pan ni
    menus pegados al nombre de la empresa.

    Devuelve un dict con title/company/location/description, o None.
    """
    for etiqueta in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(etiqueta.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        for item in (data if isinstance(data, list) else [data]):
            if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                continue

            org = item.get("hiringOrganization")
            company = org.get("name") if isinstance(org, dict) else None

            lugar = item.get("jobLocation")
            if isinstance(lugar, list):
                lugar = lugar[0] if lugar else None
            direccion = lugar.get("address") if isinstance(lugar, dict) else None
            partes = []
            if isinstance(direccion, dict):
                partes = [direccion.get("addressLocality"), direccion.get("addressRegion")]

            return {
                "title": item.get("title"),
                "company": company,
                "location": ", ".join(p for p in partes if p) or None,
                "description": _html_a_texto(item.get("description"))[:4000],
            }
    return None


async def scrape_job_by_url(url):
    """Extrae una sola oferta desde su URL. Devuelve dict o None."""
    url = sanear_url(url)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context, page = await _new_page(browser)
        try:
            if "computrabajo.com" in url:
                url = await _resolver_ficha_computrabajo(page, url)
                if url is None:
                    return None
            log(f"[URL] analizando {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            soup = BeautifulSoup(await page.content(), "html.parser")

            fuente = _fuente_de(url)
            # Si hay tarjetas de oferta, esto es un listado y no una ficha.
            if fuente == "CompuTrabajo" and soup.select("article.box_offer"):
                log("[URL] esto es un listado de resultados, no una oferta.")
                return None

            # Los datos estructurados son la fuente preferida: los sitios los
            # publican para los buscadores y no dependen de clases CSS, que en
            # Laborum son nombres generados ("sc-VigVT") y cambian solos.
            datos = _extraer_json_ld(soup)
            if datos and datos.get("title") and datos.get("description"):
                log("[URL] usando datos estructurados JSON-LD.")
                return _job(datos.get("title"), datos.get("company"),
                            datos.get("location"), "Manual", url,
                            datos.get("description"), fuente)
            log("[URL] sin JSON-LD utilizable; caigo a los selectores del sitio.")

            title = company = description = location = None

            if "linkedin.com" in url:
                source = "LinkedIn"
                title_tag = soup.find("h1") or soup.find("h2", class_=re.compile(r".*title.*"))
                company_tag = soup.find("a", class_=re.compile(r".*company.*")) or soup.find(
                    "span", class_=re.compile(r".*company.*")
                )
                desc_tag = soup.find("div", class_=re.compile(r".*description.*")) or soup.find(
                    "section", class_=re.compile(r".*description.*")
                )
                if title_tag:
                    title = title_tag.get_text(strip=True)
                if company_tag:
                    company = company_tag.get_text(strip=True)
                if desc_tag:
                    description = desc_tag.get_text(separator=" ", strip=True)[:config.MAX_DESCRIPCION]

            elif "trabajando.cl" in url:
                source = "Trabajando"
                try:
                    await page.wait_for_selector("#detalleOferta", timeout=15000)
                    await page.wait_for_timeout(2000)
                    soup = BeautifulSoup(await page.content(), "html.parser")
                except Exception:
                    log("[URL] #detalleOferta no aparecio, uso el HTML disponible.")
                title_tag = soup.find("h1") or soup.select_one("#detalleOferta h2")
                company_tag = soup.select_one("#detalleOferta .empresa") or soup.select_one(
                    "#detalleOferta span"
                )
                loc_tag = soup.select_one("#detalleOferta .ubicacion") or soup.select_one(
                    "#detalleOferta .ciudad"
                )
                desc_tag = soup.select_one("#detalleOferta")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                if company_tag:
                    company = company_tag.get_text(strip=True)
                if loc_tag:
                    location = loc_tag.get_text(strip=True)
                if desc_tag:
                    description = desc_tag.get_text(separator=" ", strip=True)[:config.MAX_DESCRIPCION]

            elif "computrabajo.com" in url:
                source = "CompuTrabajo"
                # Si hay tarjetas de oferta, esto es un listado y no una ficha.
                # Extraerlo produciria un registro con el titulo del buscador.
                if soup.select("article.box_offer"):
                    log("[URL] esto es un listado de resultados, no una oferta.")
                    return None
                title_tag = soup.find("h1")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    # El <p> que sigue al h1 trae "EMPRESA - Comuna, Region".
                    meta = title_tag.find_next_sibling("p")
                    if meta:
                        partes = meta.get_text(" ", strip=True).split(" - ", 1)
                        company = partes[0]
                        if len(partes) > 1:
                            location = partes[1]
                desc_tag = soup.select_one("p.mbB")
                if desc_tag:
                    description = desc_tag.get_text(" ", strip=True)[:config.MAX_DESCRIPCION]

            else:
                source = "Laborum"
                title_tag = soup.find("h1")
                company_tag = soup.find("h2")
                desc_tag = soup.find(
                    "div", class_=re.compile(r".*Description.*")
                ) or soup.find("div", id="descripcion-puesto")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                if company_tag:
                    company = company_tag.get_text(strip=True)
                if desc_tag:
                    description = desc_tag.get_text(separator=" ", strip=True)[:config.MAX_DESCRIPCION]

            job = _job(title, company, location, "Manual", url, description, source)
            # Si no se saco ni el titulo ni la descripcion, la extraccion fracaso:
            # mejor avisar que devolver una tarjeta vacia que la IA no podria usar.
            if job["title"] == "Sin titulo" and not job["description"]:
                log("[URL] no se pudo extraer contenido util de esta pagina.")
                return None
            return job
        except Exception as e:
            log(f"[URL] error: {e}")
            return None
        finally:
            await context.close()
            await browser.close()


# -------------------------------------------------------------------------
# Persistencia
# -------------------------------------------------------------------------

def load_db():
    """Lee jobs_db.json. Devuelve [] si no existe o esta corrupto."""
    if not config.JOBS_DB.exists():
        return []
    try:
        with open(config.JOBS_DB, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        log(f"[DB] no se pudo leer jobs_db.json ({e}). Se trata como vacia.")
        return []


def merge_jobs(old_jobs, new_jobs):
    """Fusiona resultados frescos con el historial, sin perder nada.

    Conserva 'applied', 'notes' y 'first_seen' de las ofertas ya conocidas, y
    mantiene las ofertas antiguas que no aparecieron en esta busqueda (una
    busqueda de 'SAP' no debe borrar los resultados de 'Analista').
    """
    today = date.today().isoformat()
    merged = {}

    for job in old_jobs:
        link = job.get("link")
        if link:
            merged[link] = job

    nuevas = 0
    for job in new_jobs:
        link = job["link"]
        previo = merged.get(link)
        if previo:
            # Refrescar los datos publicos, preservar tus datos.
            job["applied"] = previo.get("applied", False)
            job["notes"] = previo.get("notes", "")
            job["first_seen"] = previo.get("first_seen", today)
            # La nota de Lore, el texto del aviso y su marca de reportada se conservan.
            for campo in ("score", "score_detalle", "score_fecha", "aviso_texto", "reportada"):
                if campo in previo:
                    job[campo] = previo[campo]
        else:
            job["applied"] = False
            job["notes"] = ""
            job["first_seen"] = today
            nuevas += 1
        job["last_seen"] = today
        merged[link] = job

    # Las mas recientes primero, para verlas primero.
    ordenadas = sorted(
        merged.values(),
        key=lambda j: (j.get("first_seen", ""), j.get("title", "")),
        reverse=True,
    )
    return ordenadas, nuevas


def save_db(jobs):
    """Escritura atomica: primero a .tmp, luego reemplazo.

    Si el proceso muere a mitad de escritura, jobs_db.json queda intacto.
    """
    tmp = config.JOBS_DB.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=4, ensure_ascii=False)
    tmp.replace(config.JOBS_DB)


async def main_scrape(query, pages=1):
    """Scrapea las seis fuentes (más los sitios de sitios.json) en paralelo y fusiona con el historial.

    Devuelve True si se guardo algo, False si no hubo resultados.
    """
    global REGION, INCLUIR_REMOTO
    ajustes = regiones.cargar_ajustes(config.AJUSTES)
    REGION = regiones.region(ajustes["region"])
    INCLUIR_REMOTO = bool(ajustes.get("incluir_remoto", True))
    log(f"[Región] {REGION['nombre']}" + (" + remotos" if INCLUIR_REMOTO else ""))
    extras = cargar_sitios_extra()
    _EXTRAS_FILTRADOS_EN_URL.update(s["nombre"] for s in extras if s.get("filtra_region_en_url"))
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            resultados = await asyncio.gather(
                scrape_laborum(browser, query, pages),
                scrape_linkedin(browser, query, pages),
                scrape_trabajando(browser, query, pages),
                scrape_computrabajo(browser, query, pages),
                scrape_chiletrabajos(browser, query, pages),
                scrape_indeed(browser, query, pages),
                *(scrape_sitio(browser, query, pages, s) for s in extras),
                return_exceptions=True,
            )
        finally:
            await browser.close()

    new_jobs = []
    fuentes = ("Laborum", "LinkedIn", "Trabajando", "CompuTrabajo", "Chiletrabajos", "Indeed",
               *(s["nombre"] for s in extras))
    for fuente, res in zip(fuentes, resultados):
        if isinstance(res, Exception):
            log(f"[{fuente}] fallo completo: {res}")
        else:
            new_jobs.extend(res)

    en_region = [j for j in new_jobs if es_de_la_region(j)]
    if len(en_region) < len(new_jobs):
        log(f"[Región] descartadas {len(new_jobs) - len(en_region)} ofertas fuera de {REGION['nombre']}.")
    new_jobs = en_region

    old_jobs = load_db()

    # Guarda de seguridad: si no se obtuvo NADA, no se toca la base.
    # Asi un bloqueo de las fuentes no borra tu historial.
    if not new_jobs:
        log(
            f"[DB] cero resultados en todas las fuentes. No se escribe nada: "
            f"se conservan las {len(old_jobs)} ofertas existentes."
        )
        return False

    all_jobs, nuevas = merge_jobs(old_jobs, new_jobs)
    save_db(all_jobs)
    log(
        f"[DB] {len(all_jobs)} ofertas en total "
        f"({nuevas} nuevas en esta corrida, historial preservado)."
    )
    return True


def _cli():
    # En Windows, al redirigir la salida a una tuberia, Python usa la
    # codificacion de la consola (cp1252) y rompe las tildes del JSON. El
    # dashboard lee esta salida esperando UTF-8, asi que se fuerza aqui.
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    args = sys.argv[1:]

    if len(args) >= 2 and args[0] == "--url":
        job = asyncio.run(scrape_job_by_url(args[1]))
        if not job:
            sys.exit(1)
        # stdout limpio: solo el JSON, para que el dashboard lo parsee entero.
        print(json.dumps(job, ensure_ascii=False))
        return

    query = args[0] if args else config.DEFAULT_QUERY
    pages = 1
    if len(args) > 1:
        try:
            pages = max(1, int(args[1]))
        except ValueError:
            log(f"Paginas invalidas ('{args[1]}'), uso 1.")

    ok = asyncio.run(main_scrape(query, pages))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _cli()
