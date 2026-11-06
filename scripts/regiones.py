"""Las 16 regiones de Chile, sus comunas y cómo se busca en cada portal.

La región se elige en `ajustes.json` (carpeta de datos):

    {"region": "valparaiso", "incluir_remoto": true}

`region` es una de las claves de REGIONES, o "todo_chile" para no filtrar.
Las ofertas se filtran por el texto de su ubicación contra las comunas de la
región. Solo en la Región Metropolitana algunos portales (Laborum,
CompuTrabajo) filtran desde la URL de forma verificada; en las demás se busca
en todo Chile y el filtro por comuna decide.
"""

import json
import re
import unicodedata
from pathlib import Path

REGIONES = {
    "arica_parinacota": {
        "nombre": "Arica y Parinacota",
        "comunas": ("arica", "camarones", "putre", "general lagos", "parinacota"),
    },
    "tarapaca": {
        "nombre": "Tarapacá",
        "comunas": ("iquique", "alto hospicio", "pozo almonte", "camina", "colchane",
                    "huara", "pica", "tarapaca"),
    },
    "antofagasta": {
        "nombre": "Antofagasta",
        "comunas": ("antofagasta", "mejillones", "sierra gorda", "taltal", "calama",
                    "ollague", "san pedro de atacama", "tocopilla", "maria elena"),
        "computrabajo": "antofagasta",
    },
    "atacama": {
        "nombre": "Atacama",
        "comunas": ("copiapo", "caldera", "tierra amarilla", "chanaral", "diego de almagro",
                    "vallenar", "alto del carmen", "freirina", "huasco", "atacama"),
    },
    "coquimbo": {
        "nombre": "Coquimbo",
        "comunas": ("la serena", "coquimbo", "andacollo", "la higuera", "paiguano", "vicuna",
                    "illapel", "canela", "los vilos", "salamanca", "ovalle", "combarbala",
                    "monte patria", "punitaqui", "rio hurtado"),
    },
    "valparaiso": {
        "nombre": "Valparaíso",
        "comunas": ("valparaiso", "casablanca", "concon", "juan fernandez", "puchuncavi",
                    "quintero", "vina del mar", "isla de pascua", "los andes", "calle larga",
                    "rinconada", "san esteban", "la ligua", "cabildo", "papudo", "petorca",
                    "zapallar", "quillota", "la calera", "hijuelas", "la cruz", "nogales",
                    "san antonio", "algarrobo", "cartagena", "el quisco", "el tabo",
                    "santo domingo", "san felipe", "catemu", "llaillay", "panquehue",
                    "putaendo", "santa maria", "quilpue", "limache", "olmue", "villa alemana"),
        "computrabajo": "valparaiso",
    },
    "metropolitana": {
        "nombre": "Región Metropolitana",
        "comunas": ("santiago", "metropolitan", "metropolitana", "cerrillos", "cerro navia",
                    "conchali", "el bosque", "estacion central", "huechuraba", "independencia",
                    "la cisterna", "la florida", "la granja", "la pintana", "la reina",
                    "las condes", "lo barnechea", "lo espejo", "lo prado", "macul", "maipu",
                    "nunoa", "pedro aguirre cerda", "penalolen", "providencia", "pudahuel",
                    "quilicura", "quinta normal", "recoleta", "renca", "san joaquin",
                    "san miguel", "san ramon", "vitacura", "puente alto", "pirque",
                    "san jose de maipo", "colina", "lampa", "tiltil", "san bernardo", "buin",
                    "calera de tango", "paine", "melipilla", "alhue", "curacavi", "maria pinto",
                    "talagante", "el monte", "isla de maipo", "padre hurtado",
                    "penaflor"),
        "laborum": "en-region-metropolitana/",
        "computrabajo": "region-metropolitana-de-santiago",
        "chiletrabajos": "1022",
        "linkedin": "Santiago Metropolitan Region, Chile",
        "indeed": "Región Metropolitana",
        # Portales cuya URL ya filtra la región (verificado): no se refiltran.
        "filtrado_en_url": ("Laborum", "CompuTrabajo"),
    },
    "ohiggins": {
        "nombre": "O'Higgins",
        "comunas": ("rancagua", "codegua", "coinco", "coltauco", "donihue", "graneros",
                    "las cabras", "machali", "malloa", "mostazal", "olivar", "peumo",
                    "pichidegua", "quinta de tilcoco", "rengo", "requinoa", "san vicente",
                    "pichilemu", "la estrella", "litueche", "marchihue", "navidad", "paredones",
                    "san fernando", "chepica", "chimbarongo", "lolol", "nancagua", "palmilla",
                    "peralillo", "placilla", "pumanque", "santa cruz", "o higgins", "ohiggins"),
    },
    "maule": {
        "nombre": "Maule",
        "comunas": ("talca", "constitucion", "curepto", "empedrado", "maule", "pelarco",
                    "pencahue", "rio claro", "san clemente", "san rafael", "cauquenes",
                    "chanco", "pelluhue", "curico", "hualane", "licanten", "molina", "rauco",
                    "romeral", "sagrada familia", "teno", "vichuquen", "linares", "colbun",
                    "longavi", "parral", "retiro", "san javier", "villa alegre", "yerbas buenas"),
    },
    "nuble": {
        "nombre": "Ñuble",
        "comunas": ("chillan", "chillan viejo", "bulnes", "el carmen", "pemuco", "pinto",
                    "quillon", "san ignacio", "yungay", "quirihue", "cobquecura", "coelemu",
                    "ninhue", "portezuelo", "ranquil", "treguaco", "san carlos", "coihueco",
                    "niquen", "san fabian", "san nicolas", "nuble"),
    },
    "biobio": {
        "nombre": "Biobío",
        "comunas": ("concepcion", "coronel", "chiguayante", "hualqui", "lota",
                    "penco", "san pedro de la paz", "santa juana", "talcahuano", "tome",
                    "hualpen", "lebu", "arauco", "canete", "contulmo", "curanilahue",
                    "los alamos", "tirua", "los angeles", "antuco", "cabrero", "laja",
                    "mulchen", "nacimiento", "negrete", "quilaco", "quilleco", "san rosendo",
                    "santa barbara", "tucapel", "yumbel", "alto biobio", "biobio", "bio bio"),
        "computrabajo": "biobio",
    },
    "araucania": {
        "nombre": "La Araucanía",
        "comunas": ("temuco", "carahue", "cunco", "curarrehue", "freire", "galvarino",
                    "gorbea", "lautaro", "loncoche", "melipeuco", "nueva imperial",
                    "padre las casas", "perquenco", "pitrufquen", "pucon", "saavedra",
                    "teodoro schmidt", "tolten", "vilcun", "villarrica", "cholchol", "angol",
                    "collipulli", "curacautin", "ercilla", "lonquimay", "los sauces", "lumaco",
                    "puren", "renaico", "traiguen", "victoria", "araucania"),
    },
    "los_rios": {
        "nombre": "Los Ríos",
        "comunas": ("valdivia", "corral", "lanco", "los lagos", "mafil", "mariquina",
                    "paillaco", "panguipulli", "la union", "futrono", "lago ranco",
                    "rio bueno", "los rios"),
    },
    "los_lagos": {
        "nombre": "Los Lagos",
        "comunas": ("puerto montt", "calbuco", "cochamo", "fresia", "frutillar",
                    "los muermos", "llanquihue", "maullin", "puerto varas", "castro",
                    "ancud", "chonchi", "curaco de velez", "dalcahue", "puqueldon",
                    "queilen", "quellon", "quemchi", "quinchao", "osorno", "puerto octay",
                    "purranque", "puyehue", "rio negro", "san juan de la costa",
                    "san pablo", "chaiten", "futaleufu", "hualaihue", "palena", "chiloe",
                    "los lagos"),
    },
    "aysen": {
        "nombre": "Aysén",
        "comunas": ("coyhaique", "lago verde", "aysen", "puerto aysen", "cisnes", "guaitecas",
                    "cochrane", "o higgins", "tortel", "chile chico", "rio ibanez"),
    },
    "magallanes": {
        "nombre": "Magallanes",
        "comunas": ("punta arenas", "laguna blanca", "rio verde", "san gregorio",
                    "cabo de hornos", "puerto williams", "antartica", "porvenir", "primavera",
                    "timaukel", "natales", "puerto natales", "torres del paine", "magallanes"),
    },
}

TODO_CHILE = "todo_chile"
REMOTO = ("remoto", "remote", "teletrabajo", "home office", "100% online")


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def cargar_ajustes(ruta):
    """Lee ajustes.json. Sin archivo: Región Metropolitana con remoto incluido."""
    ajustes = {"region": "metropolitana", "incluir_remoto": True}
    ruta = Path(ruta)
    if ruta.exists():
        ajustes.update(json.loads(ruta.read_text(encoding="utf-8")))
    clave = ajustes["region"]
    if clave != TODO_CHILE and clave not in REGIONES:
        raise ValueError(f"Región desconocida en ajustes.json: {clave!r}. "
                         f"Usa una de: {', '.join(REGIONES)} o {TODO_CHILE}.")
    return ajustes


def region(clave):
    """Datos de la región (o de todo Chile) con los valores por defecto de cada portal."""
    if clave == TODO_CHILE:
        return {"clave": clave, "nombre": "todo Chile", "comunas": (), "linkedin": "Chile",
                "indeed": "Chile", "filtrado_en_url": ()}
    datos = dict(REGIONES[clave])
    datos["clave"] = clave
    datos.setdefault("linkedin", f"{datos['nombre']}, Chile")
    datos.setdefault("indeed", datos["nombre"])
    datos.setdefault("filtrado_en_url", ())
    return datos


def es_remoto(job):
    texto = normalizar(" ".join((job.get("location", ""), job.get("title", ""))))
    return any(normalizar(r) in texto for r in REMOTO)


def es_de_la_region(job, datos, incluir_remoto=True):
    """True si la oferta es de la región elegida (o remota, si se aceptan)."""
    if datos["clave"] == TODO_CHILE:
        return True
    if job.get("source") in datos["filtrado_en_url"]:
        return True
    if incluir_remoto and es_remoto(job):
        return True
    lugar = normalizar(job.get("location", ""))
    return any(re.search(rf"\b{c}\b", lugar) for c in datos["comunas"])
