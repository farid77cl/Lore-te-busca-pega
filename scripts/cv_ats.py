"""CV con normas ATS: revisa un CV escrito en Markdown y lo convierte a .docx.

Los ATS (los sistemas que filtran CVs en los portales) leen mejor un documento
simple: una sola columna, sin tablas, cuadros de texto, imágenes, íconos ni
emojis, con títulos de sección estándar y fechas consistentes. Este script
revisa esas reglas y arma el .docx con fuente y márgenes estándar.

Formato del Markdown (cv_ats.md, en la carpeta de datos):

    # Nombre Apellido
    Comuna, Región Metropolitana · correo@ejemplo.cl · linkedin.com/in/usuario

    ## Resumen profesional
    Dos a cuatro líneas.

    ## Experiencia laboral
    ### Cargo | Empresa | Ene 2019 – Abr 2026
    - Logro o función con verbo en pasado.

    ## Educación
    ### Título | Institución | 2016 – 2017

    ## Habilidades
    - Excel avanzado, SAP FI, …

Uso:
    python cv_ats.py revisar [cv_ats.md]
    python cv_ats.py docx [cv_ats.md] [--out CV_Nombre_Apellido.docx] [--telefono "+56 9 …"]

El teléfono se pasa por argumento para que no quede escrito en ningún archivo
versionado: va solo dentro del .docx.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

CV_MD = config.DATA_DIR / "cv_ats.md"

SECCIONES_OBLIGATORIAS = {
    "experiencia": "Experiencia laboral",
    "educacion": "Educación",
    "habilidades": "Habilidades",
}
SECCIONES_ESTANDAR = (
    "resumen", "perfil", "experiencia", "educacion", "formacion", "habilidades",
    "competencias", "conocimientos", "cursos", "certificaciones", "idiomas",
    "herramientas", "logros",
)
MESES = r"(ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic)[a-z]*\.?"
FECHA = re.compile(rf"({MESES}\s+)?(19|20)\d\d", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅❌✔✖⬆-⬇]")
SIMBOLOS_RAROS = re.compile(r"[★☆●◆◇■□▪▫►▶✓✔✗✘➤➢→⇒]")
TELEFONO = re.compile(r"(\+?56\s*)?9[\s.-]?\d{4}[\s.-]?\d{4}")


def _normalizar(texto):
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto.lower().strip()


def parsear(md):
    """Devuelve {'nombre', 'contacto', 'secciones': [(titulo, [bloques])]}.

    Un bloque es ('entrada', 'Cargo | Empresa | fechas'), ('vineta', texto) o
    ('parrafo', texto).
    """
    cv = {"nombre": "", "contacto": [], "secciones": []}
    actual = None
    for linea in md.splitlines():
        s = linea.strip()
        if not s or s.startswith("<!--"):
            continue
        if s.startswith("# ") and not cv["nombre"]:
            cv["nombre"] = s[2:].strip()
        elif s.startswith("## "):
            actual = (s[3:].strip(), [])
            cv["secciones"].append(actual)
        elif actual is None:
            cv["contacto"].append(s)
        elif s.startswith("### "):
            actual[1].append(("entrada", s[4:].strip()))
        elif s[:2] in ("- ", "* "):
            actual[1].append(("vineta", s[2:].strip()))
        else:
            actual[1].append(("parrafo", s))
    return cv


def revisar(md):
    """Lista de advertencias ATS. Vacía = el CV pasa."""
    avisos = []
    cv = parsear(md)
    if not cv["nombre"]:
        avisos.append("Falta el nombre como primera línea (# Nombre Apellido).")
    if not cv["contacto"]:
        avisos.append("Falta la línea de contacto bajo el nombre (comuna, correo, LinkedIn).")
    titulos = [_normalizar(t) for t, _ in cv["secciones"]]
    for clave, nombre in SECCIONES_OBLIGATORIAS.items():
        if not any(clave in t for t in titulos):
            avisos.append(f"Falta la sección «{nombre}».")
    for titulo, _ in cv["secciones"]:
        if not any(e in _normalizar(titulo) for e in SECCIONES_ESTANDAR):
            avisos.append(f"La sección «{titulo}» no tiene un nombre estándar; el ATS puede no reconocerla.")
    for titulo, bloques in cv["secciones"]:
        if "experiencia" not in _normalizar(titulo):
            continue
        for tipo, texto in bloques:
            if tipo != "entrada":
                continue
            partes = [p.strip() for p in texto.split("|")]
            if len(partes) < 3:
                avisos.append(f"«{texto}»: usa Cargo | Empresa | Fechas.")
            elif not FECHA.search(partes[-1]):
                avisos.append(f"«{texto}»: las fechas no se leen (usa «Ene 2019 – Abr 2026»).")
    if "|" in md and re.search(r"^\s*\|.*\|\s*$", md, re.M):
        avisos.append("Hay una tabla: los ATS suelen desordenarlas. Pásala a viñetas.")
    if EMOJI.search(md) or SIMBOLOS_RAROS.search(md):
        avisos.append("Hay emojis o símbolos decorativos: el ATS los lee como basura. Quítalos.")
    if re.search(r"!\[", md):
        avisos.append("Hay una imagen: el ATS no la lee y la foto no se usa en un CV ATS.")
    if TELEFONO.search(md):
        avisos.append("Hay un teléfono escrito en el archivo: pásalo con --telefono para que no quede guardado.")
    return avisos


def a_docx(md, salida, telefono=None):
    """Arma el .docx: una columna, Calibri 11, márgenes de 2 cm, sin tablas ni encabezados."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    cv = parsear(md)
    doc = Document()
    for sec in doc.sections:
        sec.top_margin = sec.bottom_margin = Cm(2)
        sec.left_margin = sec.right_margin = Cm(2)
    estilo = doc.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(11)
    estilo.paragraph_format.space_after = Pt(2)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(cv["nombre"])
    r.bold = True
    r.font.size = Pt(16)
    contacto = list(cv["contacto"])
    if telefono:
        contacto.append(telefono)
    if contacto:
        p = doc.add_paragraph(" · ".join(contacto))
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for titulo, bloques in cv["secciones"]:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        r = p.add_run(titulo.upper())
        r.bold = True
        r.font.size = Pt(12)
        for tipo, texto in bloques:
            if tipo == "entrada":
                partes = [x.strip() for x in texto.split("|")]
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(6)
                p.add_run(partes[0]).bold = True
                if len(partes) > 1:
                    p.add_run(" | " + " | ".join(partes[1:]))
            elif tipo == "vineta":
                doc.add_paragraph(texto, style="List Bullet")
            else:
                doc.add_paragraph(texto)
    doc.save(salida)
    return salida


def _cli(argv=None):
    p = argparse.ArgumentParser(description="CV con normas ATS")
    sub = p.add_subparsers(dest="cmd", required=True)
    rv = sub.add_parser("revisar")
    rv.add_argument("cv", nargs="?", default=str(CV_MD))
    dx = sub.add_parser("docx")
    dx.add_argument("cv", nargs="?", default=str(CV_MD))
    dx.add_argument("--out")
    dx.add_argument("--telefono")
    a = p.parse_args(argv)

    md = Path(a.cv).read_text(encoding="utf-8")
    avisos = revisar(md)
    for aviso in avisos:
        print(f"⚠ {aviso}")
    if a.cmd == "revisar":
        print("CV listo para ATS." if not avisos else f"{len(avisos)} cosa(s) por corregir.")
        sys.exit(1 if avisos else 0)
    nombre = parsear(md)["nombre"] or "CV"
    salida = a.out or str(Path(a.cv).with_name("CV_" + re.sub(r"\W+", "_", nombre).strip("_") + ".docx"))
    print(f"docx: {a_docx(md, salida, a.telefono)}")


if __name__ == "__main__":
    _cli()
