"""Configuración de Lore.

Los datos (base de ofertas, perfil, postulaciones, búsquedas) viven fuera de la
skill, en una carpeta de datos propia de cada persona:

  * la variable de entorno LORE_DATA, si está definida, o
  * la carpeta `lore_data/` del directorio de trabajo.

Así la skill se puede instalar en modo solo lectura y cada persona guarda sus
datos donde quiera (por ejemplo, en su propio repositorio).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LORE_DATA") or Path.cwd() / "lore_data").resolve()

# -- Rutas ---------------------------------------------------------------
JOBS_DB = DATA_DIR / "jobs_db.json"
PERFIL = DATA_DIR / "perfil.md"
POSTULACIONES = DATA_DIR / "postulaciones.md"
BUSQUEDAS = DATA_DIR / "busquedas.txt"
SITIOS = DATA_DIR / "sitios.json"
AJUSTES = DATA_DIR / "ajustes.json"
SCRAPER_PATH = BASE_DIR / "scraper.py"

# -- Scraping ------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_QUERY = "Analista Control de Gestion"
# Largo máximo de la descripción guardada. Con 3000 los requisitos solían quedar cortados.
MAX_DESCRIPCION = 12000
