import os
import sys

from . import ytdlp_loader


def main():
    # Must happen before anything imports yt_dlp.
    ytdlp_loader.activate()

    import webview

    from .api import Api
    from .server import LocalServer

    server = LocalServer()
    server.start()
    api = Api(server)

    window = webview.create_window(
        "FreeTheNoize",
        f"{server.url}/index.html",
        js_api=api,
        width=1200,
        height=780,
        min_size=(940, 620),
        background_color="#1c1c1e",
        vibrancy=sys.platform == "darwin",
        transparent=sys.platform == "darwin",
    )
    api._attach(window)
    webview.start(debug=os.environ.get("FTN_DEBUG") == "1")
    server.stop()


if __name__ == "__main__":
    main()
