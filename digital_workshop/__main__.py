"""Run the app: ``python -m digital_workshop``."""

from nicegui import ui

from digital_workshop.bootstrap import build_services
from digital_workshop.config import Settings
from digital_workshop.ui.pages import register_pages

if __name__ in {"__main__", "__mp_main__"}:
    workshop, selection = build_services(Settings.from_env())
    register_pages(workshop, selection)
    ui.run(title="Briggs Digital Workshop", reload=False)
