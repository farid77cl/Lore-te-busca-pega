import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lore_db  # noqa: E402


def oferta(link, title="Analista de Compras", company="ACME", **extra):
    base = {"title": title, "company": company, "link": link, "status": "Hace 2 días",
            "first_seen": "2026-10-19", "last_seen": "2026-10-19", "applied": False}
    base.update(extra)
    return base


def nota(score):
    return {"habilidades": 30, "nivel": 20, "sector": 15, "practico": 10, "porque": "x"} | {"total": score}


def test_edad_aviso_lee_los_formatos_de_los_portales():
    casos = {
        "Hace 3 días": 3, "Ayer": 1, "Hace 14 horas": 0, "Publicada hoy": 0,
        "1 week ago": 7, "2 months ago": 60, "Más de 30 días": 31,
        "Publicado hace más de 15 días": 16, "Actualizado hace 4 días": 4,
        "15 de Octubre de 2026": 4, "30 de septiembre": 19,
    }
    for status, esperado in casos.items():
        assert lore_db.edad_aviso(oferta("l", status=status)) == esperado, status


def test_edad_aviso_no_adivina():
    assert lore_db.edad_aviso(oferta("l", status="Manual")) is None
    assert lore_db.edad_aviso(oferta("l", status="")) is None


def test_heredar_copia_nota_y_reportada_a_la_gemela():
    jobs = [oferta("a", score=80, score_detalle=nota(80), score_fecha="2026-10-12",
                   aviso_texto="texto", reportada="2026-10-12"),
            oferta("b", title="ANALISTA DE COMPRAS", company="Acme")]
    assert lore_db.heredar(jobs) == 1
    assert jobs[1]["score"] == 80 and jobs[1]["reportada"] == "2026-10-12"
    assert jobs[1]["aviso_texto"] == "texto"


def test_pendientes_agrupa_gemelas():
    jobs = [oferta("a"), oferta("b"), oferta("c", title="Otro")]
    filas = lore_db.pendientes(jobs)
    assert len(filas) == 2
    assert filas[0]["links"] == ["a", "b"]


def test_aplicar_rechaza_60_sin_aviso_y_escribe_el_resto():
    jobs = [oferta("a"), oferta("b", title="Otro")]
    res = [{"links": ["a"], "score": 70, "score_detalle": nota(70)},
           {"links": ["b"], "score": 40, "score_detalle": nota(40)}]
    escritas, errores = lore_db.aplicar(jobs, res, "2026-10-19")
    assert escritas == 1 and len(errores) == 1
    assert "score" not in jobs[0] and jobs[1]["score"] == 40


def test_reporte_no_repite_ni_muestra_cerradas_ni_postuladas():
    jobs = [oferta("a", title="A", score=90, score_detalle=nota(90)),
            oferta("a2", title="A", score=90, score_detalle=nota(90), reportada="2026-10-12"),
            oferta("b", title="B", score=85, score_detalle=nota(85), cerrada={"fecha": "x", "evidencia": "y"}),
            oferta("c", title="C", score=80, score_detalle=nota(80), applied=True),
            oferta("d", title="D", score=78, score_detalle=nota(78)),
            oferta("e", title="E", score=65, score_detalle=nota(65))]
    elegidas, tramo = lore_db.reporte(jobs, date(2026, 10, 19))
    assert [j["link"] for j in elegidas] == ["d"] and tramo == "75+"


def test_reporte_maximo_cinco_y_respaldo_solo_si_se_pide():
    jobs = [oferta(str(i), title=f"T{i}", score=80 + i, score_detalle=nota(80)) for i in range(7)]
    elegidas, _ = lore_db.reporte(jobs, date(2026, 10, 19))
    assert len(elegidas) == 5 and elegidas[0]["score"] == 86
    medias = [oferta(str(i), title=f"M{i}", score=60 + i, score_detalle=nota(60)) for i in range(5)]
    assert lore_db.reporte(medias, date(2026, 10, 19)) == ([], "75+")
    elegidas, tramo = lore_db.reporte(medias, date(2026, 10, 19), respaldo=True)
    assert tramo == "60-74" and len(elegidas) == 3


def test_marcar_reportadas_alcanza_a_las_gemelas():
    jobs = [oferta("a", score=80), oferta("b", score=80), oferta("c", title="Otro")]
    lore_db.marcar_reportadas(jobs, [jobs[0]], "2026-10-19")
    assert jobs[1]["reportada"] == "2026-10-19" and "reportada" not in jobs[2]


def test_alertas_de_aviso_viejo_y_sin_ver():
    job = oferta("a", status="2 months ago", last_seen="2026-09-20")
    alertas = lore_db._alertas(job, date(2026, 10, 19))
    assert any("60 días" in a for a in alertas)
    assert any("2026-09-20" in a for a in alertas)


def test_cerrar_exige_evidencia():
    jobs = [oferta("a")]
    try:
        lore_db.cerrar(jobs, "a", "  ", "2026-10-19")
        assert False
    except ValueError:
        pass
    assert lore_db.cerrar(jobs, "a", "LinkedIn: «No longer accepting applications»", "2026-10-19")
    assert jobs[0]["cerrada"]["evidencia"].startswith("LinkedIn")


def test_guardar_escribe_crlf_indent_4(tmp_path):
    ruta = tmp_path / "db.json"
    lore_db.guardar([oferta("a", title="Ñandú 🤝")], ruta)
    crudo = ruta.read_bytes()
    assert crudo.startswith(b"[\r\n    {\r\n        \"title\"")
    assert b"\n" not in crudo.replace(b"\r\n", b"")
    assert json.loads(crudo.decode("utf-8"))[0]["title"] == "Ñandú 🤝"


def test_seccion_titulo_muestra_bajo_60_sin_repetir():
    jobs = [oferta("a", title="Asistente Comercial", company="A", score=58, score_detalle=nota(58)),
            oferta("b", title="ASISTENTE COMERCIAL", company="B", score=45, score_detalle=nota(45)),
            oferta("c", title="Asistente Comercial Retail", company="C", score=52, score_detalle=nota(52), reportada="2026-10-20"),
            oferta("d", title="Asistente Comercial", company="D", score=70, score_detalle=nota(70), applied=True),
            oferta("e", title="Analista", company="E", score=80, score_detalle=nota(80))]
    elegidas = lore_db.seccion_titulo(jobs, "asistente comercial")
    assert [j["link"] for j in elegidas] == ["a"]


def test_respaldo_va_aunque_haya_de_75():
    jobs = [oferta("a", title="A", score=80, score_detalle=nota(80)),
            oferta("b", title="B", score=70, score_detalle=nota(70)),
            oferta("c", title="C", score=50, score_detalle=nota(50))]
    elegidas, tramo = lore_db.reporte(jobs, date(2026, 10, 30), respaldo=True)
    assert [j["link"] for j in elegidas] == ["a", "b"] and tramo == "75+ y 60-74"
    assert lore_db.reporte(jobs, date(2026, 10, 30))[0] == [jobs[0]]


def test_agregar_salta_las_que_ya_estan():
    jobs = [oferta("a")]
    n = lore_db.agregar(jobs, [oferta("a"), {"title": "X", "company": "Y", "link": "b"}],
                        "2026-11-05", origen="correo")
    assert n == 1 and jobs[1]["origen"] == "correo" and jobs[1]["first_seen"] == "2026-11-05"
