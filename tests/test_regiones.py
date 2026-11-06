import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import regiones  # noqa: E402


def oferta(lugar, fuente="LinkedIn", titulo="Analista"):
    return {"location": lugar, "source": fuente, "title": titulo}


def test_dieciseis_regiones():
    assert len(regiones.REGIONES) == 16


def test_valparaiso_acepta_sus_comunas_y_rechaza_santiago():
    v = regiones.region("valparaiso")
    assert regiones.es_de_la_region(oferta("Viña del Mar, Valparaíso"), v)
    assert regiones.es_de_la_region(oferta("Quilpué"), v)
    assert not regiones.es_de_la_region(oferta("Las Condes, Región Metropolitana"), v)
    assert not regiones.es_de_la_region(oferta("Chile"), v)


def test_comunas_parecidas_no_se_cruzan():
    rm, bio = regiones.region("metropolitana"), regiones.region("biobio")
    assert not regiones.es_de_la_region(oferta("San Pedro de la Paz, Biobío"), rm)
    assert not regiones.es_de_la_region(oferta("La Florida, Santiago"), bio)


def test_remoto_segun_ajuste():
    v = regiones.region("valparaiso")
    job = oferta("Chile (remoto)")
    assert regiones.es_de_la_region(job, v, incluir_remoto=True)
    assert not regiones.es_de_la_region(job, v, incluir_remoto=False)


def test_rm_confia_en_la_url_de_laborum():
    rm = regiones.region("metropolitana")
    assert regiones.es_de_la_region(oferta("3.5", fuente="Laborum"), rm)
    assert not regiones.es_de_la_region(oferta("3.5", fuente="Laborum"), regiones.region("maule"))


def test_todo_chile_no_filtra():
    assert regiones.es_de_la_region(oferta("Punta Arenas"), regiones.region("todo_chile"))


def test_ajustes(tmp_path):
    assert regiones.cargar_ajustes(tmp_path / "no.json")["region"] == "metropolitana"
    ruta = tmp_path / "ajustes.json"
    ruta.write_text(json.dumps({"region": "atlantida"}), encoding="utf-8")
    with pytest.raises(ValueError):
        regiones.cargar_ajustes(ruta)
