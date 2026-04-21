"""Global hotkey listener — cross-platform via pynput (fixed for Windows)."""

import logging
import threading
from typing import Callable, Optional

from pynput import keyboard
from pynput.keyboard import KeyCode

from config import HOTKEY

logger = logging.getLogger("cluezero.hotkey")


class HotkeyListener:
    def __init__(self, callback: Callable[[], None], hotkey: Optional[str] = None):
        self.callback = callback

        raw_hotkey = (hotkey or HOTKEY).lower()
        parts = [p.strip() for p in raw_hotkey.split("+")]

        self.target_modifiers = set()
        self.target_keys = set()

        for p in parts:
            if p in ["ctrl", "shift", "alt", "cmd"]:
                self.target_modifiers.add(p)
            elif hasattr(keyboard.Key, p):
                self.target_keys.add(getattr(keyboard.Key, p))
            else:
                self.target_keys.add(KeyCode.from_char(p))

        self.pressed_modifiers = set()
        self.pressed_keys = set()

        self._debounce_lock = threading.Lock()
        self._debounce_timer: Optional[threading.Timer] = None
        self.listener: Optional[keyboard.Listener] = None

        logger.info("Hotkey registered: %s", raw_hotkey)

    def _get_mod(self, key):
        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            return "ctrl"
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            return "shift"
        if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
            return "alt"
        if key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
            return "cmd"
        return None

    def _on_press(self, key):
        mod = self._get_mod(key)
        if mod:
            self.pressed_modifiers.add(mod)
        else:
            self.pressed_keys.add(key)

        logger.info(
            "Held -> Mods: %s | Keys: %s",
            self.pressed_modifiers,
            [getattr(k, 'char', None) or getattr(k, 'vk', None) or getattr(k, 'name', None) for k in self.pressed_keys],
        )

        pressed_chars = set()
        for k in self.pressed_keys:
            if getattr(k, 'char', None):
                pressed_chars.add(k.char.lower())
            if getattr(k, 'vk', None) and 65 <= getattr(k, 'vk') <= 90:
                pressed_chars.add(chr(k.vk).lower())
            
            if not getattr(k, 'char', None):
                pressed_chars.add(k)

        target_chars = set()
        for k in self.target_keys:
            if getattr(k, 'char', None):
                target_chars.add(k.char.lower())
            if getattr(k, 'vk', None) and 65 <= getattr(k, 'vk') <= 90:
                target_chars.add(chr(k.vk).lower())
            
            if not getattr(k, 'char', None):
                target_chars.add(k)

        if self.target_modifiers.issubset(self.pressed_modifiers) and \
           target_chars.issubset(pressed_chars):
            self._trigger()

    def _on_release(self, key):
        mod = self._get_mod(key)
        if mod:
            self.pressed_modifiers.discard(mod)
        else:
            self.pressed_keys.discard(key)

    def _trigger(self):
        with self._debounce_lock:
            if self._debounce_timer and self._debounce_timer.is_alive():
                return
            self._debounce_timer = threading.Timer(0.5, lambda: None)
            self._debounce_timer.start()

        logger.info("🔥 Hotkey triggered!")
        threading.Thread(target=self.callback, daemon=True).start()

    def start(self):
        logger.info("Listening for hotkey...")
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        self.listener.join()

    def stop(self):
        if self.listener:
            self.listener.stop()