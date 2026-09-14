from types import SimpleNamespace
from unittest.mock import patch
import pytest
import launch
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


def test_listeners_are_found_even_when_windows_translates_the_state_column():
    listing = "\n".join([
        "  Proto  Local Address          Foreign Address        State           PID",
        "  TCP    127.0.0.1:8501         0.0.0.0:0              ABHÖREN         11500",
        "  TCP    127.0.0.1:8501         127.0.0.1:58514        WARTEN              0",
        "  TCP    0.0.0.0:135            0.0.0.0:0              ABHÖREN          1240",
        "  TCP    [::]:8502              [::]:0                 ABHÖREN          7788",
    ])
    with patch("launch.subprocess.run", return_value=SimpleNamespace(stdout=listing)):
        assert launch.listening_pids() == {8501: 11500, 135: 1240, 8502: 7788}


def test_only_our_own_dashboards_are_stopped():
    killed = []

    def record(command, **kwargs):
        killed.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch("launch.is_our_app", side_effect=lambda p: p == 8502), \
            patch("launch.listening_pids", return_value={8501: 111, 8502: 222}), \
            patch("launch.port_free", return_value=True), \
            patch("launch.subprocess.run", side_effect=record):
        assert launch.stop_dashboards() == ([8502], [])
    assert killed == [["taskkill", "/PID", "222", "/T", "/F"]]


def test_a_dashboard_that_refuses_to_die_is_reported_not_ignored():
    denied = SimpleNamespace(returncode=1, stdout="", stderr="Access is denied.")
    with patch("launch.is_our_app", side_effect=lambda p: p == 8501), \
            patch("launch.listening_pids", return_value={8501: 111}), \
            patch("launch.port_free", return_value=True), \
            patch("launch.subprocess.run", return_value=denied):
        assert launch.stop_dashboards() == ([], [(8501, "Access is denied.")])


def test_restart_gives_up_rather_than_starting_a_second_copy():
    with patch("launch.stop_dashboards", return_value=([], [(8501, "Access is denied.")])), \
            patch("launch.select_port") as select_port_mock, \
            patch("sys.argv", ["launch.py", "--restart"]):
        assert launch.main() == 1
    select_port_mock.assert_not_called()


def test_restart_starts_a_fresh_server_once_the_old_one_is_gone():
    with patch("launch.stop_dashboards", return_value=([8501], [])) as stop, \
            patch("launch.select_port", return_value=(8501, False)), \
            patch("launch.is_our_app", return_value=True), \
            patch("launch.subprocess.Popen") as popen, \
            patch("sys.argv", ["launch.py", "--restart", "--no-browser"]):
        popen.return_value.poll.return_value = None
        popen.return_value.wait.return_value = 0
        assert launch.main() == 0
    stop.assert_called_once()
    popen.assert_called_once()


def test_check_reports_without_stopping_anything():
    with patch("launch.select_port", return_value=(8501, True)), \
            patch("launch.stop_dashboards") as stop, \
            patch("sys.argv", ["launch.py", "--check", "--restart"]):
        assert launch.main() == 0
    stop.assert_not_called()
