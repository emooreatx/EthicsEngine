# EthicsEngine/dashboard/views/log_view.py
import asyncio
from pathlib import Path
import logging # Import logging
from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import Static, Log
from textual.message import Message
# --- FIX: Added import for escape ---
from textual.markup import escape
# --- END FIX ---

# Assume logger configures app.log in the root directory
LOG_FILE_PATH = Path("app.log")

# Import logger for internal messages
try:
    from config.config import logger
except ImportError:
    logger = logging.getLogger("LogView_Fallback")
    # logging.basicConfig(level=logging.DEBUG) # Example basic config

class LogView(Static):
    """A view to display the application's log file content."""

    log_poll_interval: reactive[float] = reactive(2.0)
    _last_log_pos: reactive[int] = reactive(0)
    _log_file: reactive[Path] = reactive(LOG_FILE_PATH)
    _read_log_task = None # Initialize task variable

    # Use the imported logger directly
    log = logger

    def __init__(self, log_file: str | Path = LOG_FILE_PATH, **kwargs):
        super().__init__(**kwargs)
        self._log_file = Path(log_file)
        self._read_log_task = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the log view."""
        yield Log(highlight=True, id="log-widget") # Corrected: removed markup=False

    def on_mount(self) -> None:
        """Called when the widget is mounted."""
        self.log.info(f"LogView mounted, monitoring {self._log_file}")
        log_widget = None
        try:
            log_widget = self.query_one(Log)
            if not self._log_file.exists():
                 try:
                     self._log_file.touch()
                     self.log.info(f"Created log file: {self._log_file}")
                     log_widget.write_line(f"--- Created log file {self._log_file} ---")
                 except OSError as e:
                     self.log.error(f"Could not create log file {self._log_file}: {e}")
                     # Use escape for the error message being written
                     log_widget.write_line(f"Error: Could not create or access log file '{escape(str(self._log_file))}'.")
                     return

            self._last_log_pos = self._log_file.stat().st_size
            # Use escape for the filename being written
            log_widget.write_line(f"--- Monitoring {escape(str(self._log_file))} ---")
            self._start_log_polling()

        except Exception as e:
             self.log.error(f"Error during LogView on_mount: {e}", exc_info=True)
             if log_widget:
                  # Use escape for the error message being written
                  log_widget.write_line(f"Error setting up log view: {escape(str(e))}")


    def on_unmount(self) -> None:
        """Called when the widget is unmounted."""
        self._stop_log_polling()

    def _start_log_polling(self) -> None:
        """Starts the asyncio task for polling the log file."""
        if self._read_log_task is None or self._read_log_task.done():
             self.log.debug("Starting log polling task...")
             self.call_later(self._read_log_updates) # Use await helper
             self._read_log_task = self.set_interval(
                  self.log_poll_interval, self._read_log_updates, pause=False
             )
             self.log.info(f"Started log polling interval ({self.log_poll_interval}s). Task: {self._read_log_task}")
        else:
             self.log.debug("Log polling task already running.")


    def _stop_log_polling(self) -> None:
        """Stops the asyncio task for polling the log file."""
        if self._read_log_task is not None:
             self.log.info(f"Stopping log polling task: {self._read_log_task}")
             try: self._read_log_task.cancel()
             except Exception as e: self.log.error(f"Error cancelling log poll task: {e}")
             self._read_log_task = None
        else: self.log.debug("Log polling task already stopped or not started.")


    async def _read_log_updates(self) -> None:
        """Reads new lines from the log file and updates the Log widget."""
        try:
            log_widget = self.query_one(Log)
            if not self._log_file.exists():
                 if log_widget.visible:
                      log_widget.write_line(f"Warning: Log file {escape(str(self._log_file))} disappeared.")
                 self.log.warning(f"Log file {self._log_file} not found during update.")
                 return

            current_size = self._log_file.stat().st_size

            if current_size < self._last_log_pos:
                 self.log.info("Log file truncated/rotated? Resetting position.")
                 if log_widget.visible:
                      log_widget.write_line(f"--- Log file truncated/rotated? Resetting position. ---")
                 self._last_log_pos = 0

            if current_size > self._last_log_pos:
                 self.log.debug(f"Log file size changed: {self._last_log_pos} -> {current_size}. Reading updates.")
                 try:
                     with open(self._log_file, "r", encoding="utf-8", errors="ignore") as f:
                         f.seek(self._last_log_pos)
                         new_content = f.read()
                         read_bytes = len(new_content.encode('utf-8', errors='ignore'))
                         self.log.debug(f"Read ~{read_bytes} bytes from log file.")
                         self._last_log_pos = f.tell()

                     if new_content:
                         if log_widget.is_mounted and log_widget.visible:
                             log_widget.write(new_content) # Use write
                             self.log.debug("Wrote new content to Log widget.")
                         else: self.log.debug("Log widget not visible/mounted, skipped writing.")

                 except FileNotFoundError:
                     self.log.error(f"Log file {self._log_file} disappeared while reading.")
                     if log_widget.visible: log_widget.write_line(f"Error: Log file {escape(str(self._log_file))} disappeared while reading.")
                 except Exception as e:
                      self.log.error(f"Error reading log file {self._log_file}: {e}", exc_info=True)
                      if log_widget.visible: log_widget.write_line(f"Error reading log file: {escape(str(e))}")

        except Exception as e:
            self.log.error(f"Error in _read_log_updates: {e}", exc_info=True)
            # self._stop_log_polling() # Optional: Stop polling on error