import threading
import pygame
from .paths import MP3_PATH


def start_music():
    """Start pygame.mixer and loop the background MP3 on a daemon thread."""
    def _run():
        try:
            pygame.mixer.init()
            if MP3_PATH.exists():
                pygame.mixer.music.load(str(MP3_PATH))
                pygame.mixer.music.play(loops=-1)
        except Exception as e:
            print(f"[Music] {e}")
    threading.Thread(target=_run, daemon=True).start()
