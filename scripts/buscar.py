"""Corre el scraper para cada búsqueda de `busquedas.txt` (una por línea).

Uso:
    python buscar.py [--paginas 2]

Las líneas vacías y las que empiezan con # se saltan. Cada búsqueda corre
el scraper completo (todos los portales) y suma a la base sin borrar nada.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402


def leer_busquedas(ruta=config.BUSQUEDAS):
    if not Path(ruta).exists():
        sys.exit(f"No encuentro {ruta}. Copia templates/busquedas.txt (y si quieres templates/sitios.json) a tu carpeta de datos.")
    lineas = Path(ruta).read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lineas if l.strip() and not l.strip().startswith("#")]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--paginas", type=int, default=2)
    a = p.parse_args()
    for q in leer_busquedas():
        print(f"=== {q}", flush=True)
        r = subprocess.run([sys.executable, str(config.SCRAPER_PATH), q, str(a.paginas)],
                           capture_output=True, text=True)
        resumen = [l for l in r.stderr.splitlines() if "[DB]" in l]
        print(resumen[-1] if resumen else "(sin resultados)", flush=True)
    print("FIN")


if __name__ == "__main__":
    main()
