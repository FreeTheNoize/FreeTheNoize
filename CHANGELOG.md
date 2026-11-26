# Changelog

## [0.4.0](https://github.com/FreeTheNoize/FreeTheNoize/releases/tag/v0.4.0) (2026-11-26)


### Novedades

* **Windows: instalador** (`FreeTheNoize-Windows-x64-Setup.exe`). No pide permisos de administrador, crea un acceso directo en el escritorio, instala Microsoft Edge WebView2 si falta, actualiza encima de la versión anterior y se desinstala sin dejar restos (tus ajustes solo si lo pides; tu música nunca).
* **macOS: imagen de disco** (`.dmg`) con «arrastra a Aplicaciones».
* **Una sola ventana**: abrir la app otra vez trae al frente la que ya está abierta.
* La primera vez se abre maximizada; después recuerda el tamaño de la ventana.


### Arreglos

* Windows: la app se abre en su propia ventana. Antes podía abrirse en el navegador, no abrirse con doble clic o cerrarse sola al arrancar.
* Si algo falla al arrancar, se avisa con la ruta del log en lugar de cerrarse sin decir nada.


### Rendimiento

* Arranque mucho más rápido: el análisis de audio se carga al usarlo, no al abrir la app.
