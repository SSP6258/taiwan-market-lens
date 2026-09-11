from pathlib import Path
from unittest.mock import patch
import pandas as pd
import sys
import pytest
from securities import snapshot_names
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


@pytest.fixture(autouse=True)
def offline_security_names():
    with patch("market.DEFAULT_SYMBOLS", [ "009805.TW", "00830.TW", "00891.TW", "00984B.TWO", "0052.TW", "009816.TW", "00685L.TW", "009820.TW", "00635U.TW", "8069.TWO"]), patch("securities.load_names", return_value=(snapshot_names(), [])):
        yield


def pick(app, kind, label):
    """Look widgets up by label. Index lookups break whenever a widget is inserted
    above them, which is exactly how the preset selectbox silently broke these tests."""
    return next(w for w in getattr(app, kind) if w.label == label)


def new_app(with_preset=False):
    """Start with the patched DEFAULT_SYMBOLS rather than a preset.

    preset_picker() applies 衝刺 on first load, replacing the selection with its own
    three symbols. That is real behaviour, but it is not what most of these tests are
    about, so they opt out and choose their own symbols.
    test_preset_applies_on_first_load covers the preset itself.
    """
    # AppTest creates a separate component registry for each runtime.
    sys.modules.pop("lightweight_chart", None)
    app = AppTest.from_file(APP)
    if not with_preset:
        app.session_state["portfolio_presets_initialized"] = True
    return app


def fixture_history(symbol, start, end):
    index = pd.bdate_range(start, end)
    frame = pd.DataFrame({"Close": [100 + i * 0.1 for i in range(len(index))]}, index=index)
    frame["Adj Close"] = frame["Close"] * 0.9
    return frame, "2026-09-08 12:00"


def test_app_controls_and_empty_state():
    with patch("market.load_symbol", side_effect=fixture_history):
        app = new_app().run(timeout=30)
        assert not app.exception
        assert len(app.metric) == 4
        assert len(app.multiselect[0].value) == 10
        assert len(app.get("bidi_component")) == 1
        pick(app, "selectbox", "價格基準").select("收盤價（未還原）").run()
        assert not app.exception
        pick(app, "segmented_control", "圖表指標").set_value("歷史回撤").run()
        assert not app.exception
        app.multiselect[0].set_value([]).run()
        assert not app.exception
        assert len(app.info) == 1


def test_partial_and_total_failure():
    def partial(symbol, start, end):
        if symbol == "009805.TW":
            raise ValueError("Test provider error")
        return fixture_history(symbol, start, end)
    with patch("market.load_symbol", side_effect=partial):
        app = new_app().run(timeout=30)
        assert not app.exception
        assert len(app.metric) == 4
        assert len(app.warning) == 1
    with patch("market.load_symbol", side_effect=ValueError("Offline")):
        app = new_app().run(timeout=30)
        assert not app.exception
        assert len(app.error) == 1


def test_add_otc_duplicate_limit_and_remove():
    with patch("market.load_symbol", side_effect=fixture_history):
        app = new_app().run(timeout=30)
        app.text_input[0].set_value("00988B")
        next(b for b in app.button if b.label == "加入上方清單").click().run()
        assert not app.exception
        assert app.multiselect[0].value[0] == "00988B.TWO"
        assert len(app.multiselect[0].value) == 11
        assert app.text_input[0].value == ""
        app.text_input[0].set_value("00988B")
        next(b for b in app.button if b.label == "加入上方清單").click().run()
        assert len(app.multiselect[0].value) == 11
        app.text_input[0].set_value("0050, 0056")
        next(b for b in app.button if b.label == "加入上方清單").click().run()
        assert not app.exception
        assert len(app.multiselect[0].value) == 11
        assert any("原清單未變更" in e.value for e in app.error)
        assert len(app.get("bidi_component")) == 1
        app.multiselect[0].set_value([s for s in app.multiselect[0].value if s != "00988B.TWO"]).run()
        assert len(app.multiselect[0].value) == 10
        assert "00988B.TWO" not in app.multiselect[0].value


def test_invalid_addition_keeps_selection_and_message():
    with patch("market.load_symbol", side_effect=fixture_history):
        app = new_app().run(timeout=30)
        original = app.multiselect[0].value.copy()
        app.text_input[0].set_value("???")
        next(b for b in app.button if b.label == "加入上方清單").click().run()
        assert not app.exception
        assert app.multiselect[0].value == original
        assert any("無效代碼" in e.value for e in app.error)
        pick(app, "selectbox", "價格基準").select("收盤價（未還原）").run()
        assert any("無效代碼" in e.value for e in app.error)


def test_added_names_appear_in_selector_and_table():
    with patch("market.load_symbol", side_effect=fixture_history):
        app = new_app().run(timeout=30)
        app.text_input[0].set_value("00908, 00998A")
        next(b for b in app.button if b.label == "加入上方清單").click().run()
        assert not app.exception
        assert app.multiselect[0].value[:2] == ["00908.TW", "00998A.TWO"]
        assert "00908 富邦入息REITs+" in app.multiselect[0].options
        assert "00998A 主動復華金融股息" in app.multiselect[0].options
        assert app.metric[0].label == "00908 富邦入息REITs+"
        assert "00998A 主動復華金融股息" in app.dataframe[0].value["標的"].tolist()


def test_common_period_explains_both_limiting_symbols():
    def shortened(symbol, start, end):
        frame, stamp = fixture_history(symbol, start, end)
        if symbol == "009816.TW":
            frame = frame.iloc[10:]
        if symbol == "0052.TW":
            frame = frame.iloc[:-5]
        return frame, stamp
    with patch("market.load_symbol", side_effect=shortened):
        app = new_app().run(timeout=30)
        assert not app.exception
        notice = next(i.value for i in app.info if "共同期間" in i.value)
        assert "009816 凱基台灣TOP50：資料自" in notice
        assert "限制共同起日" in notice
        assert "0052 富邦科技：資料截至" in notice
        assert "限制共同迄日" in notice


def test_new_default_selection():
    with patch("market.DEFAULT_SYMBOLS", ["0050.TW", "2330.TW", "2454.TW"]), patch("market.load_symbol", side_effect=fixture_history):
        app = new_app().run(timeout=30)
        assert not app.exception
        assert app.multiselect[0].value == ["0050.TW", "2330.TW", "2454.TW"]
        assert len(app.metric) == 3


def test_metric_cards_rank_by_return():
    def ranked_history(symbol, start, end):
        frame, stamp = fixture_history(symbol, start, end)
        growth = {"0050.TW": -0.1, "2330.TW": 0.2, "2454.TW": 0.4, "0052.TW": 0.1, "8069.TWO": 0.3}[symbol]
        frame["Close"] = [100 + i * growth for i in range(len(frame))]
        frame["Adj Close"] = frame["Close"]
        return frame, stamp
    with patch("market.DEFAULT_SYMBOLS", ["0050.TW", "2330.TW", "2454.TW", "0052.TW", "8069.TWO"]), patch("market.load_symbol", side_effect=ranked_history):
        app = new_app().run(timeout=30)
        assert not app.exception
        assert [m.label.split()[0] for m in app.metric] == ["2454", "8069", "2330", "0052"]


def test_preset_applies_on_first_load():
    """The preset replaces the default selection and the amount; nothing covered this,
    which is why it broke these tests unnoticed when it was added."""
    with patch("market.load_symbol", side_effect=fixture_history):
        app = new_app(with_preset=True).run(timeout=30)
        assert not app.exception
        assert app.multiselect[0].value == ["0050.TW", "2330.TW", "2454.TW"]
        assert app.session_state["investment_amount_wan"] == 1000.0
        assert len(app.metric) == 3
        pick(app, "selectbox", "預設配置").select("退休").run()
        assert not app.exception
        assert app.multiselect[0].value == ["009816.TW", "00662.TW", "00984B.TWO", "00685L.TW"]
        assert app.session_state["investment_amount_wan"] == 3000.0
