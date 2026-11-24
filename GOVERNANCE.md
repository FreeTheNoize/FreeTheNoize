# Gobierno del proyecto

FreeTheNoize es un proyecto comunitario y **horizontal**: nadie es dueño del código y las decisiones se toman entre
quienes lo mantienen y lo usan. Las reglas de abajo existen para que eso funcione sin que el proyecto dependa de una
sola persona ni se pueda romper por un descuido o por mala fe.

## Para qué existe

Dar a DJs y a la escena una herramienta libre para conseguir música de SoundCloud **a la mejor calidad que exista**,
sin recodificar, **diciendo la verdad sobre esa calidad** (falsos lossless, loudness, corte de frecuencias) y lista
para pinchar (BPM, tonalidad, etiquetas). Libre de anuncios, de cuentas y de telemetría. Y respetando a los artistas:
es para uso personal y no sirve para saltarse lo que cada artista decide sobre su música.

Una propuesta que se aleje de esto (rastreo de usuarios, monetización, recodificar "para ahorrar espacio",
esquivar protecciones de pago de forma masiva…) se rechaza aunque esté bien programada.

## Roles

| Rol | Quién | Puede |
|---|---|---|
| **Comunidad** | Cualquiera | Abrir issues, discusiones y PR desde un fork; comentar y probar PR |
| **Contributors** (equipo `contributors`) | Personas aceptadas por quienes ya colaboran | Crear ramas en el repo, triar issues, **aprobar y fusionar PR** (su aprobación cuenta igual que la de un maintainer), votar incorporaciones |
| **Maintainers** (equipo `maintainers`) | Contributors con recorrido en el proyecto | Lo mismo, y además cuidar el repo: etiquetas, hotfixes, ajustes de GitHub, seguridad y votar los cambios grandes |

Para fusionar una PR basta **1 aprobación de un maintainer o de un contributor** distinto de quien la abre.
Nadie aprueba lo suyo, tampoco quien fundó el proyecto.

Las personas **owners** de la organización GitHub son como mínimo dos, elegidas entre los maintainers. Su papel es
**solo ejecutar** lo que se decide (invitar o retirar gente, secretos, ajustes de seguridad), porque GitHub no deja
hacerlo de otra manera. No tienen más voto ni pueden saltarse las reglas.

### Entrar

Las nuevas incorporaciones las aceptan quienes ya colaboran:

- **Contributor**: cualquier maintainer o contributor propone a alguien (o alguien se propone) en una Discussion de la
  categoría *Gobierno*, enlazando lo que ha aportado (PR, revisiones, issues, ayuda a otras personas). Está abierta
  **7 días** y se acepta con el apoyo explícito (👍 o comentario) de **al menos dos personas del equipo** —maintainers o
  contributors; si aún son menos de dos, de todas— y **ninguna objeción razonada** sin resolver.
- **Maintainer**: igual, pero entre contributors con recorrido, y con el apoyo de **al menos dos maintainers**
  (o de todos, si aún son menos de dos).
- Una owner ejecuta la decisión (añade a la persona al equipo) y lo anota en la Discussion y en la lista de abajo.

### Salir

- Cualquiera puede dejarlo cuando quiera; se le agradece y pasa a *emeritus* en la lista de abajo.
- Tras **6 meses** sin actividad se retiran los permisos (se recuperan pidiéndolo). Es higiene de seguridad, no un castigo.
- Por saltarse el [código de conducta](CODE_OF_CONDUCT.md), según lo que diga ese documento.
- Retirar a alguien por otro motivo se decide como un cambio grande (ver abajo), sin que vote la persona afectada.

## Cómo se decide

1. **Consenso perezoso** para el día a día: una PR con 1 aprobación y los checks en verde se puede fusionar.
   Si alguien tiene dudas fundadas, comenta y se espera.
2. **Cambios grandes** (dirección del proyecto, dependencias pesadas, cambios de API, licencia, estas mismas reglas):
   propuesta en una Discussion de *Gobierno*, al menos **7 días** abierta.
3. Si no hay acuerdo, **votan los maintainers**: gana la mayoría simple de quienes votan, con un mínimo de la mitad
   del equipo participando. Un cambio de licencia o de este documento necesita **dos tercios**.

## Salvaguardas técnicas

Lo que impide que el proyecto "se vaya a la mierda", configurado en GitHub y no solo escrito aquí:

- `main` y `develop` protegidas con *rulesets*: sin pushes directos, sin force-push y sin borrar la rama.
- Todo entra por PR con **al menos 1 aprobación de otra persona**; un push después de aprobar obliga a aprobar de nuevo,
  y las conversaciones abiertas bloquean el merge.
- A `main` solo llegan PR desde `develop`, `hotfix/*` o la PR de release del bot.
- Checks obligatorios: tests en Linux/macOS/Windows, título Conventional Commit, rama de origen y revisión de dependencias.
- **CODEOWNERS**: toda PR pide revisión a `maintainers` y `contributors`; solo cuenta la aprobación de alguien de esos equipos distinto de quien la abre.
- Etiquetas `v*` inmutables (no se pueden mover ni borrar) y builds/imágenes con atestación de procedencia.
- Las PR de forks de gente nueva necesitan aprobación para ejecutar workflows; el `GITHUB_TOKEN` es de solo lectura por defecto
  y las acciones de terceros están fijadas por SHA (Dependabot las actualiza).
- Escaneo de secretos con bloqueo en push, Dependabot y CodeQL activos.

**Nadie tiene bypass** de estas reglas, tampoco quien fundó el proyecto. Si hace falta saltárselas en una emergencia
(p. ej. un secreto filtrado), un owner lo hace, lo deja escrito en una Discussion de *Gobierno* en 24 h y restaura la regla.

## Personas

| Persona | Rol |
|---|---|
| [@quim-d](https://github.com/quim-d) | Maintainer (fundador) |

*Emeritus*: nadie todavía.
