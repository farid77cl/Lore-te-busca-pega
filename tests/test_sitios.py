import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import scraper  # noqa: E402

SITIO = {
    "nombre": "Bolsa X", "url": "https://bolsax.cl/buscar?q={query}&p={page}&o={offset}",
    "base": "https://bolsax.cl", "tarjeta": "div.oferta", "titulo": "h2 a",
    "empresa": ".empresa", "ubicacion": ".lugar", "fecha": ".fecha", "por_pagina": 10,
}

HTML = """
<div class="oferta"><h2><a href="/o/1">Analista de Compras</a></h2>
  <span class="empresa">ACME</span><span class="lugar">Providencia</span><span class="fecha">Hoy</span></div>
<div class="oferta"><h2><a href="/o/1">Analista de Compras</a></h2></div>
<div class="oferta"><h2><a href="https://otra.cl/o/2">Asistente Comercial</a></h2></div>
<div class="oferta"><p>sin título</p></div>
"""


def test_url_sitio_reemplaza_marcadores():
    url = scraper.url_sitio(SITIO, "Analista de Compras", 3)
    assert url == "https://bolsax.cl/buscar?q=Analista+de+Compras&p=3&o=20"


def test_parsear_sitio_saca_campos_y_no_repite():
    jobs = scraper.parsear_sitio(HTML, SITIO)
    assert [j["link"] for j in jobs] == ["https://bolsax.cl/o/1", "https://otra.cl/o/2"]
    assert jobs[0]["company"] == "ACME" and jobs[0]["location"] == "Providencia"
    assert jobs[0]["source"] == "Bolsa X"
    assert jobs[1]["company"] == "Empresa Confidencial"


def test_cargar_sitios_salta_inactivos_e_incompletos(tmp_path):
    ruta = tmp_path / "sitios.json"
    ruta.write_text(json.dumps([SITIO, dict(SITIO, nombre="Off", activo=False), {"nombre": "Roto"}]),
                    encoding="utf-8")
    assert [s["nombre"] for s in scraper.cargar_sitios_extra(ruta)] == ["Bolsa X"]


def test_region_de_un_sitio_extra():
    job = {"source": "Bolsa X", "location": "Valparaíso"}
    assert not scraper.es_de_la_region(job)
    scraper._EXTRAS_FILTRADOS_EN_URL.add("Bolsa X")
    try:
        assert scraper.es_de_la_region(job)
    finally:
        scraper._EXTRAS_FILTRADOS_EN_URL.discard("Bolsa X")
