import threading
import pygame
from .paths import MP3_PATH


def start_music():
    """Inicia pygame.mixer i toca el MP3 en bucle infinit en un thread daemon."""
    def _run():
        try:
            pygame.mixer.init()
            if MP3_PATH.exists():
                pygame.mixer.music.load(str(MP3_PATH))
                pygame.mixer.music.play(loops=-1)
        except Exception as e:
            print(f"[Music] Error: {e}")
    threading.Thread(target=_run, daemon=True).start()
