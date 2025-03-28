# EthicsEngine/dashboard/views/__init__.py
from .run_config_view import RunConfigurationView
from .results_view import ResultsView
from .data_mgmt_view import DataManagementView
from .results_browser_view import ResultsBrowserView
from .config_view import ConfigurationView

# This makes it easy to import all views using "from dashboard.views import *"
# or specific views like "from dashboard.views import ResultsView"
__all__ = [
    "RunConfigurationView",
    "ResultsView",
    "DataManagementView",
    "ResultsBrowserView",
    "ConfigurationView",
]