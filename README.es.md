<h1 align="center">Sylenara Hub</h1>

<p align="center"><a href="./README.md">English</a> · <strong>Español</strong></p>

<p align="center">
Extensiones (y, con el tiempo, widgets y más) para la shell <a href="https://github.com/iMacnucintosh/sylenara-shell">Sylenara</a>, y el catálogo que lee <strong>Things</strong>.
</p>

## Qué hay

| Extensión | Qué hace |
| --- | --- |
| [`tasks`](extensions/tasks) | Lista de tareas en el carrusel del dashboard |
| [`hydration`](extensions/hydration) | Control del agua que bebes, con recordatorios |
| [`games`](extensions/games) | Tu biblioteca de Steam en el dashboard: perfil, logros, sesiones y calendario de actividad |
| [`vpn-forticlient`](extensions/vpn-forticlient) | Conexiones VPN FortiClient (openfortivpn) en Ajustes → Red, con códigos OTP y certificados de cliente |

El catálogo completo, con versiones, enlaces de descarga y `sha256`, está en [`index.json`](index.json).

## Instalar una extensión

Con **Things** (sección **Sylenara**): pulsa una extensión para ver su ficha (descripción, capturas, requisitos, qué toca en tu equipo y novedades) y después **Instalar**. Pide confirmación y, solo si la extensión necesita permisos de administrador, tu contraseña. Desde una terminal: `syl ext list`, `syl ext install <zip>` y `syl ext remove <id> [--purge]`.

Para un zip suelto: en Things, **Instalar desde zip**, o `syl ext install <zip>`. Quitarla (papelera, con la casilla opcional de borrar sus ajustes y datos) elimina también lo que instaló como administrador.

## La ficha de cada extensión (`store/`)

Lo que Things enseña al abrir una extensión (descripción larga, puntos destacados, novedades por versión, enlaces y capturas) vive en `extensions/<id>/store/` y **no va dentro del zip**:

- `details.json`: `about`, `highlights` (hasta 6), `author`, `license`, `links` (`source`, `issues`, `web`; solo https), `changelog` (`version`, `date`, `changes`) y `screenshots` (`file` + `caption`).
- `screenshots/`: imágenes png, jpg o webp de hasta 1,5 MB (máximo 6). Sin datos personales: usa datos de ejemplo.
- `i18n/<idioma>.json`: texto en inglés → traducción, para todo lo anterior.

`scripts/build.py` valida todo y genera `store/<id>.json` (lo que descarga Things); el índice lo enlaza. Los **requisitos** (`requires`) y lo que **toca en el equipo** (`system`, `data`) salen del manifiesto, sin escribirlos dos veces.

## Para quien publique aquí

Cada extensión es una carpeta `extensions/<id>/` con su `manifest.json` (ver el `AGENTS.md` de Sylenara, sección «Extensiones»). Las reglas del proyecto valen también aquí:

- **i18n siempre:** todo texto visible va por `Tr.*` y se traduce; el catálogo de la extensión vive en `i18n/es.json`.
- **Nada privado:** ni credenciales, ni hosts, ni datos de tu red. La configuración de cada persona vive en su `shell.json` y en sus propios ficheros.

```sh
scripts/build.py            # genera dist/<id>-<versión>.zip y reescribe index.json
scripts/build.py --check    # comprueba que index.json y store/ están al día y que ninguna versión publicada cambió de zip (para CI)
python3 -m unittest discover -s tests   # tests (fichas, zips, scripts de Juegos)
scripts/publish.sh <id>     # publica el zip como release <id>-<versión>
```

Para sacar una versión nueva: sube `version` en el manifiesto, `scripts/build.py`, commit, `scripts/publish.sh <id>`. Los zips son deterministas: las mismas fuentes dan los mismos bytes.

## Licencia

GPL-3.0, como Sylenara (ver [`LICENSE`](LICENSE)). Copyright (C) 2026 Manuel López Mallorquín.
