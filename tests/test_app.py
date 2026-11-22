"""Runs the Streamlit app headlessly in demo mode."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


def test_app_demo_search():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    at.button[-1].click().run()  # "Find resorts"
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert labels == ["Hotels found", "Meet all criteria", "Excluded"]
    assert int(at.metric[0].value) > 0
