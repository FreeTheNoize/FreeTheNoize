# Seguridad

## Versiones con soporte

Solo la **última release** publicada (y la imagen `latest`). Si usas una anterior, actualiza antes de reportar.

## Cómo reportar una vulnerabilidad

**No abras un issue público.** Usa el reporte privado de GitHub:
[Security → Report a vulnerability](../../security/advisories/new).

Incluye qué versión y modo (escritorio o servicio/Docker), cómo reproducirlo y el impacto que ves.
Lo verán solo los maintainers. Intentamos contestar en **7 días** y acordar contigo cuándo se publica el aviso;
se te da crédito si quieres.

## Qué nos importa especialmente

- **Modo servicio**: acceso sin `FTN_PASSWORD`, lectura o escritura fuera de la carpeta de música o de datos,
  inyección a través de nombres de archivo, etiquetas o enlaces, problemas con `FTN_TRUSTED_PROXIES`.
- **Credenciales**: fugas del token de SoundCloud o de la contraseña.
- **Cadena de suministro**: el autoactualizador de yt-dlp, el aviso de nueva versión y los artefactos de las releases.

Puedes comprobar que un zip o una imagen salen de nuestro CI:

```sh
gh attestation verify FreeTheNoize-macOS-AppleSilicon.zip -R FreeTheNoize/FreeTheNoize
gh attestation verify oci://ghcr.io/freethenoize/freethenoize:latest -R FreeTheNoize/FreeTheNoize
```
