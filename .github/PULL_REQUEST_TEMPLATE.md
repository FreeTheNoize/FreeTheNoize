<!-- La PR va contra `develop`. El título sigue Conventional Commits: `fix: …`, `feat: …`, `docs: …` (ver CONTRIBUTING.md). -->

## Qué cambia y por qué

Closes #

## Cómo se ha probado

- [ ] `pytest` en local
- [ ] Probado en escritorio (sistema: …)
- [ ] Probado en modo servicio / Docker

## Arquitectura (ver AGENTS.md y ARCHITECTURE.md)

- [ ] La función nueva es un complemento (generado con `python tools/new_plugin.py`), no código en el kernel
- [ ] La página usa solo la API `FTN` (`registerView`, `GET/POST`, `h()`…), sin `fetch` directo ni HTML con datos
- [ ] `python tools/check_architecture.py` pasa sin errores (y sin `ftn-arch: allow` nuevos, o explicados aquí)

## Checklist

- [ ] Un solo propósito por PR
- [ ] Tests añadidos o ajustados si cambia el comportamiento
- [ ] README actualizado si cambia algo visible para quien lo usa
- [ ] Sin telemetría ni llamadas nuevas a terceros
- [ ] Sin recodificar audio
