import ctypes
import os
import platform

arch = platform.architecture()[0]
dll_name = f"nvdaControllerClient{'32' if arch == '32bit' else '64'}.dll"
# Construct absolute path to the DLL in the parent directory
dll = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), dll_name
)
nvda = ctypes.windll.LoadLibrary(dll)


def speak(msg):
    # Test if nvda is running
    try:
        running = nvda.nvdaController_testIfRunning()
        if running == 0:  # 0 usually means NVDA is running
            nvda.nvdaController_speakText(msg)
    except Exception:
        pass
