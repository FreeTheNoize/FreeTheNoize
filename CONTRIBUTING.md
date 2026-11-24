# Cómo contribuir a FreeTheNoize

Gracias por querer meter mano. FreeTheNoize es de quien lo usa y lo mejora: no hay jefe, hay revisión entre iguales.
Lee también el [código de conducta](CODE_OF_CONDUCT.md) y [cómo se toman las decisiones](GOVERNANCE.md).

## Antes de empezar

- **Bugs**: abre un [issue](../../issues/new/choose) con la plantilla. Versión, sistema y el enlace que falla ayudan mucho.
- **Ideas o cambios grandes** (una pestaña nueva, otra fuente de descarga, cambiar la API): abre primero una
  [Discussion](../../discussions) o un issue para hablarlo. Evita que trabajes en algo que luego no encaje.
- **Fallos de seguridad**: nunca en un issue público. Mira [SECURITY.md](SECURITY.md).
- Busca primero si ya existe. Los issues con `good first issue` son buen punto de entrada.

## Ramas

```
feature/…, fix/…  ──PR──▶  develop  ──PR (release)──▶  main  ──▶  vX.Y.Z
                                                     ▲
                                hotfix/… ────PR──────┘  (solo arreglos urgentes)
```

| Rama | Para qué | Quién escribe |
|---|---|---|
| `develop` | Rama por defecto. Aquí van **todas** las PR. | Solo por PR con 1 aprobación y los checks en verde |
| `main` | Lo que está publicado. Cada merge propone una release. | Solo PR desde `develop`, `hotfix/*` o la PR de release |
| `hotfix/*` | Arreglo urgente sobre una versión publicada. | Maintainers |

**No se aceptan PR directas a `main`**: el check *Source branch* las bloquea. Si te equivocas de base, cámbiala a `develop` en la propia PR.

## Paso a paso

1. Haz un fork (o, si eres del equipo, una rama en el repo) desde `develop`:
   `git switch -c fix/descripcion-corta origin/develop`
2. Entorno:
   ```sh
   uv venv && uv pip install -e ".[desktop,dev]"
   .venv/bin/python -m pytest
   ```
3. Cambios **pequeños y con un solo propósito**. Mejor tres PR cortas que una gigante.
4. Si cambias comportamiento, añade o ajusta **tests** en `tests/`.
5. Abre la PR contra **`develop`** y rellena la plantilla.
6. El **título de la PR** sigue [Conventional Commits](https://www.conventionalcommits.org/es/), porque es el mensaje
   del commit final y de él sale el CHANGELOG y la versión:

   | Prefijo | Cuándo | Versión |
   |---|---|---|
   | `feat: …` | funcionalidad nueva | minor (3.**2**.0) |
   | `fix: …` | arreglo | patch (3.1.**1**) |
   | `perf:`, `refactor:`, `docs:`, `test:`, `build:`, `ci:`, `chore:` | resto | no publica por sí solo |
   | `feat!: …` o `BREAKING CHANGE:` en el cuerpo | rompe compatibilidad | major (**4**.0.0) |

   Ejemplos: `fix: el token de SoundCloud caducado no reintenta`, `feat(library): filtro por género`.

7. Espera la revisión. Se fusiona con **squash** cuando hay **1 aprobación** de un maintainer o contributor y los checks están en verde.

## Qué se revisa

- Que funcione en **escritorio y en modo servicio** (Docker), y en macOS, Windows y Linux si toca algo del sistema.
- Que **no se recodifique** el audio: el principio del proyecto es bajar siempre la mejor fuente tal cual.
- Que no se rompa la etiqueta de calidad real ni el análisis (corte de frecuencias, LUFS, BPM/tonalidad).
- **Seguridad del modo servicio**: nada que exponga rutas fuera de la carpeta de música o se salte `FTN_PASSWORD`.
- **Privacidad**: ni telemetría, ni analítica, ni llamadas a terceros nuevas sin hablarlo antes.
- Dependencias nuevas: justificadas, mantenidas y con licencia compatible con **GPL-2.0-or-later**.
- La UI sigue siendo HTML/CSS/JS **sin build**.

Los cambios en CI (`.github/`), empaquetado, `Dockerfile`, dependencias o el actualizador se revisan con lupa:
son lo que acaba ejecutándose en el ordenador de quien usa la app.

## Revisar PR de otras personas

Revisar es contribuir tanto como programar. Cualquier persona puede comentar; la aprobación que cuenta para fusionar es la de
alguien de `maintainers` o `contributors` (ver [GOVERNANCE.md](GOVERNANCE.md) para unirte).

- Prueba el cambio si puedes (`gh pr checkout <n>`), no solo leas el diff.
- Sé concreto y amable: qué falla, por qué y, si puedes, cómo lo harías.
- **Nadie aprueba su propia PR.** Si después de tu aprobación se suben cambios, hace falta aprobar de nuevo.
- Si no lo ves claro, pide otra opinión en vez de aprobar por compromiso.

## Releases

No hay que hacer nada a mano:

1. Un maintainer o contributor abre la PR `develop → main` y otra persona la aprueba.
2. Al llegar a `main`, el bot abre o actualiza la **PR de release** (`chore: release X.Y.Z`) con la versión y el CHANGELOG.
   **Esa PR es la revisión de la release**: se comprueba que la versión y las notas son correctas.
3. Al fusionarla se crea la etiqueta `vX.Y.Z`, la release de GitHub con los zips de escritorio (y `SHA256SUMS.txt`)
   y la imagen `ghcr.io/freethenoize/freethenoize:X.Y.Z` / `latest`, todo con atestación de procedencia.
4. El bot abre una PR `main → develop` (back-merge). Se fusiona con **merge commit**, no squash.

La imagen `:edge` se publica en cada cambio de `develop`, para quien quiera probar lo último.

## Licencia

Al contribuir aceptas que tu aportación se publica bajo la [GPL-2.0-or-later](LICENSE), como el resto del proyecto.
