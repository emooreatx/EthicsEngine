# EthicsEngine/dashboard/views/log_view.py
"""
Provides a Textual view for displaying and tailing the application's log file.
"""
import asyncio
from pathlib import Path
import logging # Import logging
# --- Textual Imports ---
from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import Static, Log # Log widget for displaying logs
from textual.message import Message
from textual.markup import escape # For safely displaying file paths

# --- Constants and Logger ---
# Default path to the application log file
LOG_FILE_PATH = Path("app.log")

# Use the application's configured logger if available
try:
    from config.config import logger
except ImportError:
    # Fallback logger if config isn't available
    logger = logging.getLogger("LogView_Fallback")

# --- View Class ---
class LogView(Static):
    """
    A Textual view widget that displays the content of a log file
    and automatically tails it for new updates.
    """

    # --- Reactive Attributes ---
    log_poll_interval: reactive[float] = reactive(2.0) # How often to check for log updates (seconds)
    _last_log_pos: reactive[int] = reactive(0) # Last read position in the log file
    _log_file: reactive[Path] = reactive(LOG_FILE_PATH) # Path to the log file being monitored
    _read_log_task = None # Holds the asyncio task for polling

    # Use the imported logger for internal logging of this view's actions
    log = logger

    def __init__(self, log_file: str | Path = LOG_FILE_PATH, **kwargs):
        """
        Initializes the LogView.

        Args:
            log_file: The path to the log file to monitor. Defaults to LOG_FILE_PATH.
            **kwargs: Additional arguments for the Static widget.
        """
        super().__init__(**kwargs)
        self._log_file = Path(log_file)
        self._read_log_task = None # Initialize task as None

    def compose(self) -> ComposeResult:
        """Compose the UI: just the Log widget."""
        # The Log widget handles scrolling and rendering efficiently.
        yield Log(highlight=True, id="log-widget")

    def on_mount(self) -> None:
        """Called when the widget is mounted. Starts log polling."""
        self.log.info(f"LogView mounted, monitoring {self._log_file}")
        log_widget = None
        try:
            log_widget = self.query_one(Log) # Get the Log widget instance
            # Ensure the log file exists, create it if not
            if not self._log_file.exists():
                 try:
                     self._log_file.touch() # Create the file if it doesn't exist
                     self.log.info(f"Created log file: {self._log_file}")
                     log_widget.write_line(f"--- Created log file {self._log_file} ---")
                 except OSError as e:
                     # Handle errors creating the log file (e.g., permissions)
                     self.log.error(f"Could not create log file {self._log_file}: {e}")
                     log_widget.write_line(f"Error: Could not create or access log file '{escape(str(self._log_file))}'.")
                     return # Stop if file cannot be accessed/created

            # Store the initial size to read only new content
            self._last_log_pos = self._log_file.stat().st_size
            log_widget.write_line(f"--- Monitoring {escape(str(self._log_file))} ---")
            # Start the background polling task
            self._start_log_polling()

        except Exception as e:
             # Log errors during mount process
             self.log.error(f"Error during LogView on_mount: {e}", exc_info=True)
             if log_widget:
                  # Display error in the log widget itself if possible
                  log_widget.write_line(f"Error setting up log view: {escape(str(e))}")


    def on_unmount(self) -> None:
        """Called when the widget is unmounted. Stops log polling."""
        self.log.info("LogView unmounted, stopping polling.")
        self._stop_log_polling()

    def _start_log_polling(self) -> None:
        """Starts the asyncio task that periodically reads log updates."""
        # Check if the task isn't already running
        if self._read_log_task is None or self._read_log_task.done():
             self.log.debug("Starting log polling task...")
             # Read immediately once, then start the interval
             self.call_later(self._read_log_updates) # Schedule immediate check
             self._read_log_task = self.set_interval(
                  self.log_poll_interval, self._read_log_updates, pause=False
             )
             self.log.info(f"Started log polling interval ({self.log_poll_interval}s). Task: {self._read_log_task}")
        else:
             self.log.debug("Log polling task already running.")


    def _stop_log_polling(self) -> None:
        """Stops the asyncio task that polls the log file."""
        if self._read_log_task is not None:
             self.log.info(f"Stopping log polling task: {self._read_log_task}")
             try:
                 self._read_log_task.cancel() # Cancel the scheduled interval task
             except Exception as e:
                 self.log.error(f"Error cancelling log poll task: {e}")
             self._read_log_task = None # Clear the task reference
        else:
             self.log.debug("Log polling task already stopped or not started.")


    async def _read_log_updates(self) -> None:
        """
        Reads new content from the log file since the last check and updates the Log widget.
        Handles file truncation/rotation by resetting the read position.
        """
        try:
            log_widget = self.query_one(Log) # Get the Log widget
            # Check if the log file still exists
            if not self._log_file.exists():
                 if log_widget.visible: # Only write warning if widget is visible
                      log_widget.write_line(f"Warning: Log file {escape(str(self._log_file))} disappeared.")
                 self.log.warning(f"Log file {self._log_file} not found during update.")
                 return # Stop checking if file is gone

            # Get current file size
            current_size = self._log_file.stat().st_size

            # Handle file truncation (e.g., log rotation)
            if current_size < self._last_log_pos:
                 self.log.info("Log file truncated/rotated? Resetting position.")
                 if log_widget.visible:
                      log_widget.write_line(f"--- Log file truncated/rotated? Resetting position. ---")
                 self._last_log_pos = 0 # Reset position to start of file

            # If file has grown, read the new content
            if current_size > self._last_log_pos:
                 self.log.debug(f"Log file size changed: {self._last_log_pos} -> {current_size}. Reading updates.")
                 try:
                     # Open the file, seek to the last known position, and read the rest
                     with open(self._log_file, "r", encoding="utf-8", errors="ignore") as f:
                         f.seek(self._last_log_pos)
                         new_content = f.read()
                         # Update the last known position (using tell() is more reliable after read)
                         self._last_log_pos = f.tell()
                         read_bytes = len(new_content.encode('utf-8', errors='ignore')) # Approx bytes read
                         self.log.debug(f"Read ~{read_bytes} bytes from log file.")

                     # If new content was read, write it to the Log widget
                     if new_content:
                         # Check if widget is mounted and visible before writing
                         if log_widget.is_mounted and log_widget.visible:
                             log_widget.write(new_content) # Use write() for potentially multiple lines
                             self.log.debug("Wrote new content to Log widget.")
                         else:
                             self.log.debug("Log widget not visible/mounted, skipped writing.")

                 except FileNotFoundError:
                     # Handle rare case where file disappears between size check and open
                     self.log.error(f"Log file {self._log_file} disappeared while reading.")
                     if log_widget.visible: log_widget.write_line(f"Error: Log file {escape(str(self._log_file))} disappeared while reading.")
                 except Exception as e:
                      # Log other file reading errors
                      self.log.error(f"Error reading log file {self._log_file}: {e}", exc_info=True)
                      if log_widget.visible: log_widget.write_line(f"Error reading log file: {escape(str(e))}")

        except Exception as e:
            # Catch-all for errors within the update task itself
            self.log.error(f"Error in _read_log_updates: {e}", exc_info=True)
            # Optionally stop polling on error:
            # self._stop_log_polling()
