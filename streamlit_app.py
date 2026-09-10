"""Compatibility entrypoint for the existing Streamlit Cloud deployment."""
from pathlib import Path
import runpy
import sys

app_dir = Path(__file__).resolve().parent / "app"
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))
runpy.run_path(str(app_dir / "streamlit_app.py"), run_name="__main__")
