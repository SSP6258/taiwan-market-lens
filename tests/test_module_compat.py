from unittest.mock import patch
from types import SimpleNamespace
from module_compat import load_renderer


def test_old_cloud_module_reloads_before_new_arguments():
    old = SimpleNamespace(render_beta=lambda a,b,c,d,e,f: None)
    current = SimpleNamespace(render_beta=lambda a,b,c,d,e,f,weights=None,portfolio_name=None: weights)
    with patch('module_compat.importlib.reload', return_value=current) as reload, patch('module_compat.importlib.import_module', return_value=old):
        render = load_renderer('beta_analysis','render_beta','weights')
        assert render(1,2,3,4,5,6,[.6,.2,.2],'custom') == [.6,.2,.2]
        reload.assert_called_once_with(old)


def test_current_module_is_not_reloaded():
    current = SimpleNamespace(render_analysis=lambda weights=None: weights)
    with patch('module_compat.importlib.reload') as reload, patch('module_compat.importlib.import_module', return_value=current):
        assert load_renderer('correlation','render_analysis','weights') is current.render_analysis
        reload.assert_not_called()
