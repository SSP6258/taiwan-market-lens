from unittest.mock import patch
import pytest
from launch import select_port


def test_reuse_existing_dashboard_before_starting_another():
    with patch("launch.is_our_app", side_effect=lambda p: p == 8503):
        assert select_port() == (8503, True)


def test_skip_occupied_port():
    with patch("launch.is_our_app", return_value=False), patch("launch.port_free", side_effect=lambda p: p == 8502):
        assert select_port() == (8502, False)


def test_all_ports_busy_has_clear_error():
    with patch("launch.is_our_app", return_value=False), patch("launch.port_free", return_value=False):
        with pytest.raises(RuntimeError, match="all busy"):
            select_port()
