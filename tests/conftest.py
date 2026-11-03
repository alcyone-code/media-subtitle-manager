import os
import sys


# backend/app 를 import 경로에 추가 (subtitle_utils 직접 import)
BACKEND_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "app"))
if BACKEND_APP_DIR not in sys.path:
    sys.path.insert(0, BACKEND_APP_DIR)
