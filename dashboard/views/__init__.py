# EthicsEngine/dashboard/views/__init__.py
from .run_config_view import RunConfigurationView
# from .results_view import ResultsView # Removed unused import causing error
from .data_mgmt_view import DataManagementView
from .results_browser_view import ResultsBrowserView
from .log_view import LogView

# This makes it easy to import all views using "from dashboard.views import *"
# or specific views like "from dashboard.views import ResultsBrowserView"
__all__ = [
    "RunConfigurationView",
    # "ResultsView", # Removed from __all__
    "DataManagementView",
    "ResultsBrowserView",
    "LogView",
]
