"""Real pop-up windows for the SoundCloud sign-in window.

SoundCloud signs in through pop-ups (Google, Facebook, Apple, and its own
web-auth page) that talk back to the opener with postMessage. pywebview
never lets a page open a real pop-up: it sends the URL to the system browser
(which on Windows ends up as an "about:blank" link nobody can open) or blocks
it. These patches let pop-ups opened from the sign-in window become real
child windows that share its cookies, and leave every other window alone.
"""
import sys

_login_windows: set = set()
_installed = False


def allow_popups(window) -> None:
    """Let `window` (a pywebview Window) open real pop-up windows."""
    install()
    _login_windows.add(window)


def forget(window) -> None:
    _login_windows.discard(window)


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    try:
        if sys.platform == "win32":
            _install_edgechromium()
        elif sys.platform == "darwin":
            _install_cocoa()
    except Exception:  # never break the app over this
        import logging

        logging.getLogger(__name__).exception("could not enable sign-in pop-ups")


def _install_edgechromium() -> None:
    from webview.platforms import edgechromium

    original = edgechromium.EdgeChrome.on_new_window_request

    def on_new_window_request(self, sender, args):
        if self.pywebview_window in _login_windows:
            # Not handled: WebView2 opens its own pop-up window in the same
            # profile, with window.opener intact.
            return
        original(self, sender, args)

    edgechromium.EdgeChrome.on_new_window_request = on_new_window_request


def _install_cocoa() -> None:
    import AppKit
    import objc
    import WebKit
    from webview.platforms import cocoa

    open_popups = []  # keep the windows and their delegates alive

    class FTNPopupDelegate(AppKit.NSObject):
        def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
                self, webview, config, action, features):
            return _open_popup(config)

        def webViewDidClose_(self, webview):
            for entry in list(open_popups):
                if entry[1] is webview:
                    entry[0].close()
                    open_popups.remove(entry)

    def _open_popup(config):
        rect = AppKit.NSMakeRect(0, 0, 520, 720)
        style = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable
                 | AppKit.NSWindowStyleMaskResizable)
        win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, AppKit.NSBackingStoreBuffered, False)
        win.setReleasedWhenClosed_(False)
        win.setTitle_("Iniciar sesión")
        view = WebKit.WKWebView.alloc().initWithFrame_configuration_(rect, config)
        delegate = FTNPopupDelegate.alloc().init()
        view.setUIDelegate_(delegate)
        win.setContentView_(view)
        win.center()
        win.makeKeyAndOrderFront_(None)
        open_popups.append((win, view, delegate))
        return view

    delegate_cls = cocoa.BrowserView.BrowserDelegate
    original = delegate_cls.webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_

    def create_web_view(self, webview, config, action, features):
        for window in _login_windows:
            view = cocoa.BrowserView.instances.get(window.uid)
            if view is not None and view.webview is webview:
                return _open_popup(config)
        return original(self, webview, config, action, features)

    objc.classAddMethods(delegate_cls, [objc.selector(
        create_web_view,
        selector=b"webView:createWebViewWithConfiguration:forNavigationAction:windowFeatures:",
        signature=original.signature,
    )])
