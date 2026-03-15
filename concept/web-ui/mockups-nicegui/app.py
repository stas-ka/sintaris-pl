"""Pico Bot — NiceGUI mockup application entry point.

Run:  python app.py
Then open http://localhost:8080 in a browser.

Requires:  pip install nicegui
"""

import sys
from pathlib import Path

# Ensure the mockups-nicegui directory is on the module search path
sys.path.insert(0, str(Path(__file__).parent))

from nicegui import ui

# Import all page modules — their @ui.page decorators register routes on import
import page_admin   # noqa: F401  /admin
import page_calendar  # noqa: F401  /calendar
import page_chat    # noqa: F401  /chat
import page_dashboard  # noqa: F401  /  (home)
import page_mail    # noqa: F401  /mail
import page_notes   # noqa: F401  /notes
import page_voice   # noqa: F401  /voice

ui.run(
    title="Pico Bot",
    dark=True,
    port=8080,
    reload=True,
)
