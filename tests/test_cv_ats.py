import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cv_ats  # noqa: E402

BUENO = """# Ana Pérez
Providencia, Región Metropolitana · ana@correo.cl

## Resumen profesional
Analista con 10 años en retail.

## Experiencia laboral
### Analista de Proveedores | Empresa Uno | Ene 2019 – Abr 2026
- Concilié cuentas de proveedores en SAP.

## Educación
### Diplomado en Finanzas | Universidad X | 2016 – 2017

## Habilidades
- Excel avanzado
"""


def test_cv_bueno_pasa():
    assert cv_ats.revisar(BUENO) == []


def test_detecta_lo_que_rompe_un_ats():
    malo = BUENO.replace("## Habilidades", "## Mis superpoderes 🚀") \
        .replace("Ene 2019 – Abr 2026", "hace harto") + "\n| a | b |\n+56 9 1234 5678\n"
    avisos = " ".join(cv_ats.revisar(malo))
    for esperado in ("Habilidades", "nombre estándar", "fechas", "tabla", "emojis", "teléfono"):
        assert esperado in avisos, esperado


def test_docx_trae_el_texto_y_el_telefono_solo_ahi(tmp_path):
    from docx import Document
    salida = cv_ats.a_docx(BUENO, tmp_path / "cv.docx", telefono="+56 9 0000 0000")
    texto = "\n".join(p.text for p in Document(salida).paragraphs)
    assert "Ana Pérez" in texto and "EXPERIENCIA LABORAL" in texto
    assert "+56 9 0000 0000" in texto and "Concilié cuentas" in texto
    assert not Document(salida).tables
