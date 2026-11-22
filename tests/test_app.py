"""Runs the Streamlit app headlessly in demo mode."""
import shutil
import tempfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


def test_app_collects_once_then_filters_without_new_calls():
    shutil.rmtree(Path(tempfile.gettempdir()) / "resortfinder-demo", ignore_errors=True)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    collect = [b for b in at.button if b.label.startswith("Collect hotels")]
    assert collect, "first visit should offer to collect the area"
    collect[0].click().run()
    assert not at.exception
    assert [m.label for m in at.metric] == ["Hotels saved", "Meet all criteria", "Excluded"]
    passed_at_45 = int(at.metric[1].value)

    at.slider[0].set_value(4.0).run()  # minimum rating: filtering only
    assert not at.exception
    assert int(at.metric[1].value) >= passed_at_45
    assert any(b.label == "Refresh from the web" for b in at.button)
