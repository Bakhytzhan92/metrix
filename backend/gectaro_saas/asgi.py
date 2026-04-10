from pathlib import Path
import os

from django.core.asgi import get_asgi_application

BASE_DIR = Path(__file__).resolve().parent.parent

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gectaro_saas.settings")

application = get_asgi_application()

