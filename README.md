# Lore te busca pega 🤝 🇨🇱

**Asistente de IA gratis y de código abierto para buscar trabajo en Chile.** Te arma un **CV con normas ATS**, busca ofertas de empleo en **Laborum, CompuTrabajo, LinkedIn, Trabajando.cl, Chiletrabajos e Indeed**, las califica según tu perfil y te ayuda a postular. Es una skill para **Claude** (Claude Code y claude.ai).

![Licencia MIT](https://img.shields.io/badge/licencia-MIT-green) ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue) ![Hecho en Chile](https://img.shields.io/badge/hecho%20en-Chile%20🇨🇱-red) ![Claude skill](https://img.shields.io/badge/Claude-skill-orange)

> **Hecha para buscar trabajo en Chile**, en cualquiera de las 16 regiones o en todo el país, con portales chilenos, sueldos en pesos líquidos y el vocabulario de los avisos de acá.

**Lore te busca pega** es una skill para Claude que te acompaña a buscar trabajo **desde cero**: aunque no tengas CV, no sepas qué cargos buscar ni cuánto pedir de sueldo. No es headhunter ni reclutadora: no trabaja para ninguna empresa, trabaja para ti.

Habla como una amiga chilena normal: cercana, simpática y con chispa, cero cuica ni arribista. Es chistosa, buena para tirar la talla sana y tirar para arriba el ánimo cuando la búsqueda se pone pesada, pero súper derecha y estricta con la verdad: lo que no está en tu perfil no existe.

## Qué hace

- **Arma o reescribe tu CV con normas ATS.** Si tienes CV, lo lee; si no, te lo arma con una entrevista corta. Lo deja listo para los filtros automáticos de los portales (una columna, títulos estándar, palabras clave de los avisos reales, sin tablas ni íconos) y te entrega un .docx.
- **Te ayuda a decidir qué buscar** a partir de lo que ya hiciste, y cuánto pedir según lo que pagan los avisos.
- **Busca ofertas** en Laborum, LinkedIn, Trabajando, CompuTrabajo, Chiletrabajos e Indeed, **en tu región** (o en todo Chile), con o sin trabajos remotos. Puedes **agregar más sitios** sin tocar código.
- **Califica cada oferta** con una pauta fija: habilidades 40, nivel 25, sector 20, lo práctico 15. Revisa los requisitos excluyentes primero: un título exigido que no tienes deja la oferta bajo 60.
- **Te muestra solo lo que vale la pena:** hasta 5 ofertas de 75 o más, más un respaldo de 60 a 74, sin repetir nunca una oferta ya mostrada.
- **Lee tu correo** (opcional, con el conector de Gmail): alertas de empleo y respuestas de reclutadores. Nunca envía ni borra nada.
- **Te acompaña al postular y te ayuda con las preguntas en línea:** Te ofrece redactar las respuestas para las preguntas de filtro de los avisos y portales (Trabajando, Laborum, Indeed, CompuTrabajo, Buk, AIRA, HiringRoom), listas para copiar y pegar según tu perfil real (sueldo pretendido, experiencia concreta, motivación). Lleva el registro de tus postulaciones y te recuerda el seguimiento a los 7 y 14 días.

## Cómo partir

1. Instala la skill (abajo).
2. Escríbele: «Lore, ayúdame a buscar trabajo».
3. Ella te guía, una pregunta a la vez: tu CV, qué buscas, en qué región, cuánto quieres ganar. No necesitas saber programar: la parte técnica la hace ella.

## Requisitos

- **Python 3.10 o más**
- Paquetes de Python: `playwright`, `playwright-stealth`, `beautifulsoup4`, `python-docx` (y `pytest` para las pruebas). Están todos en `scripts/requirements.txt`.
- **Chromium** para Playwright: `python -m playwright install chromium`
- Para la búsqueda automática, un entorno que ejecute Python y abra un navegador: Claude Code en tu computador o en la nube. En un chat sin código, Lore igual arma tu CV, califica los avisos que le pegues y te ayuda a postular.
- Opcional: el conector de **Gmail**.

Lore revisa los requisitos y los instala ella misma cuando puede.

## Instalación

### En Claude Code

```bash
git clone https://github.com/farid77cl/Lore-te-busca-pega ~/.claude/skills/lore-te-busca-pega
pip install -r ~/.claude/skills/lore-te-busca-pega/scripts/requirements.txt
python -m playwright install chromium
```

### En claude.ai

Comprime la carpeta (con `SKILL.md` en la raíz del zip) y súbela en la sección de Skills de la configuración de claude.ai.

## Tus datos

Tus datos no viven en la skill sino en tu **carpeta de datos**: `lore_data/` en el directorio donde trabajas, o la que indiques en la variable `LORE_DATA`. Ahí quedan tu perfil, tu CV, tus búsquedas, tu región (`ajustes.json`), la base de ofertas y el registro de postulaciones.

**Este repositorio es público; tus datos, no.** Nunca subas tu carpeta de datos a este repo ni a un fork público: el `.gitignore` ya bloquea `lore_data/`, tu perfil, tu CV, tu base de ofertas y tus postulaciones. Si quieres respaldar tus datos con git, usa un repositorio **privado** aparte; Lore hace commit ahí después de cada revisión.

No guardes en el perfil tu teléfono, RUT ni fecha de nacimiento: el teléfono se pone solo al generar el .docx.

## Tu región

```json
{"region": "biobio", "incluir_remoto": true}
```

Regiones: `arica_parinacota`, `tarapaca`, `antofagasta`, `atacama`, `coquimbo`, `valparaiso`, `metropolitana`, `ohiggins`, `maule`, `nuble`, `biobio`, `araucania`, `los_rios`, `los_lagos`, `aysen`, `magallanes`, o `todo_chile`. Las ofertas se filtran por comuna (la lista está en `scripts/regiones.py`). Lore te pregunta la región al empezar, así que no necesitas tocar este archivo.

## Agregar más sitios

¿Usas la bolsa de empleo de tu municipalidad, de tu universidad o de tu rubro? Dile a Lore «agrega este sitio» con el link de una búsqueda hecha ahí. Ella revisa la página, arma la entrada en `sitios.json` y la prueba. Si quieres hacerlo tú, la explicación de cada campo está en `SKILL.md` y la plantilla en `templates/sitios.json`.

Los sitios que piden iniciar sesión para ver las ofertas no se pueden agregar.

## El correo

Para que Lore lea tus alertas y las respuestas de reclutadores, conecta Gmail en los Conectores de la configuración de claude.ai. Es opcional: sin correo, puedes pegarle las alertas o mandarle capturas.

## Estructura

```
SKILL.md              instrucciones de Lore (la skill)
scripts/scraper.py    scraper de los seis portales + los de sitios.json
scripts/regiones.py   las 16 regiones de Chile y sus comunas
scripts/buscar.py     corre todas las búsquedas de busquedas.txt
scripts/lore_db.py    la base: heredar, pendientes, aplicar, reporte, cerrar, agregar
scripts/cv_ats.py     revisa el CV contra las normas ATS y lo arma en .docx
scripts/config.py     rutas (carpeta de datos)
templates/            perfil, CV, ajustes, búsquedas, sitios extra y registro de postulaciones
tests/                pruebas
```

Pruebas: `python -m pytest tests -q`.

## Preguntas frecuentes

**¿Qué es un CV ATS y por qué lo necesito?**
La mayoría de los portales de empleo en Chile (Laborum, Trabajando, CompuTrabajo, Buk, HiringRoom) filtran los CV con un ATS, un sistema que los lee como texto antes de que los vea una persona. Si tu CV tiene tablas, columnas o íconos, el ATS no lo entiende y quedas fuera. Lore lo arma en el formato que el ATS sí lee.

**¿Sirve si no tengo experiencia o no tengo CV?**
Sí. Lore te hace una entrevista corta y arma tu primer CV con tus estudios, tu práctica, voluntariados, emprendimientos o trabajos por temporada.

**¿Sirve fuera de Santiago?**
Sí: busca en cualquiera de las 16 regiones de Chile, en todo el país o solo trabajos remotos.

**¿Lore postula por mí?**
No. Te muestra las ofertas que valen la pena y te ayuda a responder cada formulario, pero postular lo decides y lo haces tú.

**¿Es gratis?**
La skill sí (licencia MIT). Necesitas una cuenta de Claude para usarla.

**¿Qué pasa con mis datos?**
Quedan en tu computador o en tu sesión, en tu carpeta de datos. Nunca se suben a este repositorio, y Lore no te pide contraseñas.

## English

**Lore te busca pega** ("Lore finds you a job") is an open-source Claude skill for job seekers in Chile. It rewrites your résumé to pass ATS filters, scrapes Chilean job boards (Laborum, CompuTrabajo, LinkedIn, Trabajando.cl, Chiletrabajos, Indeed) for any of Chile's 16 regions, scores each posting 0–100 against your real profile, optionally reads your Gmail for job alerts and recruiter replies, and proactively helps you craft tailored answers for online application questions (screening questions on job boards) without making anything up. The skill speaks warm, friendly, everyday Chilean Spanish.

## Contribuir

¿Un portal cambió su HTML, falta una comuna o quieres sumar un sitio que sirva a todos? Abre un issue o un pull request. Antes de enviarlo, corre `python -m pytest tests -q`, y nunca incluyas datos personales (perfiles, CVs ni bases de ofertas reales).

## Licencia

MIT. Úsala, cópiala y adáptala libremente.

## Límites conocidos

- Solo Chile.
- Fuera de la Región Metropolitana, algunos portales no filtran por región en la búsqueda: se busca en todo Chile y se filtra por comuna, así que llegan menos ofertas por búsqueda.
- Indeed bloquea los navegadores de la nube; desde tu computador debería funcionar.
- Los portales cambian su HTML de vez en cuando; si una fuente deja de traer ofertas, las otras siguen funcionando.
