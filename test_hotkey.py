import sys
import logging
logging.basicConfig(level=logging.INFO)
sys.path.insert(0, "./client")
from hotkey import HotkeyListener
print("Imports succeeded!")
try:
    h = HotkeyListener(lambda: print("Triggered"))
    print("Init succeeded!")
except Exception as e:
    import traceback
    traceback.print_exc()
