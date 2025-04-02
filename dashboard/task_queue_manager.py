import asyncio
import traceback
import uuid
import os
from pathlib import Path
import argparse # For ArgsNamespace if needed directly, or passed from app

# Import necessary components from Textual or pass app instance
# from textual.app import App - Avoid direct App import if possible
from textual.widgets import ListView, ListItem, Label # For type hinting if needed

# Import backend logic and utils (relative imports assuming structure)
from .dashboard_utils import load_json, save_json, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, BENCHMARKS_FILE, DATA_DIR, RESULTS_DIR, ArgsNamespace # Added ArgsNamespace import
from config.config import logger, semaphore # Import logger (correct name) and semaphore
# Import run functions
from .run_scenario_pipelines import run_all_scenarios_async, run_and_save_single_scenario
from .run_benchmarks import run_benchmarks_async, run_and_save_single_benchmark, load_benchmarks
# ArgsNamespace is now imported from dashboard_utils above


class TaskQueueManager:
    def __init__(self, app_instance):
        """
        Initializes the TaskQueueManager.

        Args:
            app_instance: The instance of the main EthicsEngineApp.
        """
        self.app = app_instance # Store reference to the main app
        # State is managed via app's reactive properties:
        # self.app.task_queue
        # self.app.is_queue_processing

    def _update_task_status(self, task_id: str, new_status: str, message: str | None = None):
        """Finds a task by ID in the app's queue and updates its status."""
        current_queue = list(self.app.task_queue) # Work with a copy
        updated = False
        for task in current_queue:
            if task.get('id') == task_id:
                task['status'] = new_status
                if message: task['message'] = message # Optional message (e.g., error details)
                updated = True
                break
        if updated:
            self.app.task_queue = current_queue # Trigger reactive update by assigning the modified list
            logger.info(f"Updated status for task {task_id} to {new_status}") # Use logger
        else:
            logger.warning(f"Could not find task with ID {task_id} to update status.") # Use logger

    # --- Task Execution Logic ---

    async def _execute_single_task(self, task_details: dict):
        """Executes a single scenario or benchmark task."""
        task_id = task_details.get('id')
        args_obj = task_details.get('args')
        item_dict = task_details.get('item_dict')
        task_type = task_details.get('task_type') # "Ethical Scenarios" or "Benchmarks"
        item_id = task_details.get('item_id')

        if not all([task_id, args_obj, item_dict, task_type, item_id]):
             self._update_task_status(task_id, "Error", "Missing task details for execution.")
             return

        self._update_task_status(task_id, "Running")
        saved_output_file = None
        try:
            if not isinstance(args_obj, ArgsNamespace):
                 logger.error(f"Task {task_id}: args_obj is not ArgsNamespace type. Recreating.") # Use logger
                 args_obj = ArgsNamespace(
                      data_dir=DATA_DIR, results_dir=RESULTS_DIR,
                      species=task_details.get('species'), model=task_details.get('model'),
                      reasoning_level=task_details.get('depth'),
                      bench_file=BENCHMARKS_FILE, scenarios_file=SCENARIOS_FILE
                 )

            logger.info(f"Executing Task {task_id}: Single {task_type} ID {item_id}") # Use logger

            if task_type == "Ethical Scenarios":
                saved_output_file = await run_and_save_single_scenario(item_dict, args_obj)
            elif task_type == "Benchmarks":
                saved_output_file = await run_and_save_single_benchmark(item_dict, args_obj)
            else:
                raise ValueError(f"Invalid task type '{task_type}' in task details")

            if saved_output_file:
                self._update_task_status(task_id, "Completed", f"Saved to {os.path.basename(saved_output_file)}")
                self.app.notify(f"Task {item_id} complete. Saved to {os.path.basename(saved_output_file)}.", title="Task Success", timeout=5)
            else:
                self._update_task_status(task_id, "Warning", "Run finished, but failed to save results.")
                self.app.notify(f"Task {item_id} finished, but failed to save results. Check logs.", title="Save Warning", severity="warning", timeout=8)

        except Exception as e:
             error_msg = f"Runtime Error: {e}"
             self._update_task_status(task_id, "Error", error_msg)
             self.app.notify(f"Error running task {item_id}: {e}", severity="error")
             logger.error(f"Runtime Error executing task {task_id}: {e}\n{traceback.format_exc()}") # Use logger

    async def _execute_all_scenarios(self, task_details: dict):
        """Executes the run_all_scenarios task."""
        task_id = task_details.get('id')
        args_obj = task_details.get('args')

        if not task_id or not args_obj:
             self._update_task_status(task_id, "Error", "Missing task details for execution.")
             return

        self._update_task_status(task_id, "Running")
        saved_output_file = None
        try:
            logger.info(f"Executing Task {task_id}: All Scenarios") # Use logger
            saved_output_file = await run_all_scenarios_async(cli_args=args_obj)

            if saved_output_file:
                self._update_task_status(task_id, "Completed", f"Saved to {os.path.basename(saved_output_file)}")
                self.app.notify(f"All Scenarios run complete. Saved to {os.path.basename(saved_output_file)}.", title="Task Success", timeout=8)
            else:
                self._update_task_status(task_id, "Warning", "Run finished, but failed to save results.")
                self.app.notify("All Scenarios run finished, but failed to save results. Check logs.", title="Warning", severity="warning", timeout=8)

        except Exception as e:
             error_msg = f"Runtime Error: {e}"
             self._update_task_status(task_id, "Error", error_msg)
             self.app.notify(f"Error running all scenarios: {e}", severity="error")
             logger.error(f"Runtime Error executing task {task_id} (all scenarios): {e}\n{traceback.format_exc()}") # Use logger

    async def _execute_all_benchmarks(self, task_details: dict):
        """Executes the run_benchmarks task."""
        task_id = task_details.get('id')
        args_obj = task_details.get('args')

        if not task_id or not args_obj:
             self._update_task_status(task_id, "Error", "Missing task details for execution.")
             return

        self._update_task_status(task_id, "Running")
        saved_output_file = None
        try:
            logger.info(f"Executing Task {task_id}: All Benchmarks") # Use logger
            saved_output_file = await run_benchmarks_async(cli_args=args_obj)

            if saved_output_file:
                self._update_task_status(task_id, "Completed", f"Saved to {os.path.basename(saved_output_file)}")
                self.app.notify(f"All Benchmarks run complete. Saved to {os.path.basename(saved_output_file)}.", title="Task Success", timeout=8)
            else:
                self._update_task_status(task_id, "Warning", "Run finished, but failed to save results.")
                self.app.notify("All Benchmarks run finished, but failed to save results. Check logs.", title="Warning", severity="warning", timeout=8)

        except Exception as e:
             error_msg = f"Runtime Error: {e}"
             self._update_task_status(task_id, "Error", error_msg)
             self.app.notify(f"Error running all benchmarks: {e}", severity="error")
             logger.error(f"Runtime Error executing task {task_id} (all benchmarks): {e}\n{traceback.format_exc()}") # Use logger

    # --- Queue Management ---

    async def action_start_queue(self):
        """Processes the tasks in the app's queue sequentially."""
        if self.app.is_queue_processing:
            self.app.notify("Queue is already processing.", severity="warning")
            return
        if not self.app.task_queue:
            self.app.notify("Queue is empty.", severity="info")
            return

        self.app.is_queue_processing = True
        self.app.loading = True # Use app's loading indicator
        self.app.run_status = "Processing Queue..."
        logger.info("Starting queue processing...") # Use logger

        # Create a snapshot of the queue to process
        queue_to_process = list(self.app.task_queue)

        for task in queue_to_process:
            if task.get('status') in ['Completed', 'Error', 'Warning']:
                 logger.debug(f"Skipping task {task.get('id')} with status {task.get('status')}") # Use logger
                 continue

            task_id = task.get('id')
            task_type = task.get('type')

            try:
                if task_type == 'single':
                    await self._execute_single_task(task)
                elif task_type == 'all_scenarios':
                    await self._execute_all_scenarios(task)
                elif task_type == 'all_benchmarks':
                    await self._execute_all_benchmarks(task)
                else:
                    self._update_task_status(task_id, "Error", f"Unknown task type: {task_type}")
                    logger.error(f"Unknown task type '{task_type}' for task ID {task_id}") # Use logger

                # Optional delay
                # await asyncio.sleep(0.1)

            except Exception as e:
                error_msg = f"Queue processing error: {e}"
                if task_id:
                    self._update_task_status(task_id, "Error", error_msg)
                logger.error(f"Error during queue processing loop for task {task_id}: {e}", exc_info=True) # Use logger
                # Decide whether to continue or stop the queue on error
                # break # Uncomment to stop queue on first error

        # Queue finished
        self.app.is_queue_processing = False
        self.app.loading = False
        self.app.run_status = "Queue Processing Finished"
        logger.info("Queue processing finished.") # Use logger
        self.app.notify("Finished processing all tasks in the queue.", title="Queue Complete")

        # Filter out completed/errored tasks from the queue view
        current_queue = list(self.app.task_queue)
        # Keep only tasks that are NOT 'Completed' or 'Error'
        filtered_queue = [
            task for task in current_queue
            if task.get('status') not in ['Completed', 'Error']
        ]
        # Only update the reactive property if the list actually changed
        if len(filtered_queue) != len(current_queue):
            self.app.task_queue = filtered_queue
            logger.info(f"Filtered queue: Removed {len(current_queue) - len(filtered_queue)} completed/errored tasks.")
        else:
            logger.info("Queue filtering: No completed/errored tasks found to remove.")


        # Refresh results browser once at the end
        try:
            # Need to import ResultsBrowserView here or pass it differently
            from .views.results_browser_view import ResultsBrowserView
            browser_view = self.app.query_one(ResultsBrowserView)
            browser_view._populate_file_list()
            logger.info("Results browser refreshed after queue completion.") # Use logger
        except Exception as browse_e:
            self.app.log.warning(f"Could not refresh browser list after queue: {browse_e}") # Use app's logger

    def action_clear_queue(self):
        """Clears all tasks from the app's queue."""
        if self.app.is_queue_processing:
            self.app.notify("Cannot clear queue while it's processing.", severity="warning")
            return

        if not self.app.task_queue:
            self.app.notify("Queue is already empty.", severity="info")
            return

        self.app.task_queue = [] # Clear the app's reactive list
        logger.info("Task queue cleared.") # Use logger
        self.app.notify("Queue cleared.", title="Queue Cleared")

    def add_task_to_queue(self, task_details: dict):
        """Adds a validated task dictionary to the app's queue."""
        # Add a unique ID if not present (though button handler should add it)
        if 'id' not in task_details:
            task_details['id'] = str(uuid.uuid4())
        if 'status' not in task_details:
            task_details['status'] = 'Pending'

        # Append to the app's reactive list
        self.app.task_queue = self.app.task_queue + [task_details]
        logger.info(f"Added task {task_details.get('id')} to queue.") # Use logger
        # Notification is handled by the button press handler in the main app
