"""
Manages the execution of tasks added to the dashboard's queue.

Handles running single items (scenarios or benchmarks), full scenario sets,
or full benchmark sets asynchronously. Updates task status in the UI
and manages the overall queue processing state.
"""
import asyncio
import traceback
import uuid
import os
from pathlib import Path
import argparse

# Import necessary components from Textual
from textual.widgets import ListView, ListItem, Label

from .dashboard_utils import load_json, save_json, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, BENCHMARKS_FILE, DATA_DIR, RESULTS_DIR, ArgsNamespace
from config.config import logger, semaphore
from .run_scenario_pipelines import run_all_scenarios_async, run_and_save_single_scenario
from .run_benchmarks import run_benchmarks_async, run_and_save_single_benchmark, load_benchmarks


class TaskQueueManager:
    """
    Manages the lifecycle and execution of tasks in the dashboard's queue.

    This class interacts with the main application (`EthicsEngineApp`) to access
    the task queue (a reactive list) and update task statuses. It contains
    methods to execute different types of tasks (single item, all scenarios,
    all benchmarks) by calling the appropriate backend run functions.
    """
    def __init__(self, app_instance):
        """
        Initializes the TaskQueueManager.

        Args:
            app_instance: The instance of the main EthicsEngineApp.
        """
        self.app = app_instance

    def _update_task_status(self, task_id: str, new_status: str, message: str | None = None):
        """Finds a task by ID in the app's queue and updates its status."""
        current_queue = list(self.app.task_queue)
        updated = False
        for task in current_queue:
            if task.get('id') == task_id:
                task['status'] = new_status
                if message: task['message'] = message
                updated = True
                break
        if updated:
            self.app.task_queue = current_queue
            logger.info(f"Updated status for task {task_id} to {new_status}")
        else:
            logger.warning(f"Could not find task with ID {task_id} to update status.")


    async def _execute_single_task(self, task_details: dict):
        """Executes a single scenario or benchmark task."""
        task_id = task_details.get('id')
        args_obj = task_details.get('args')
        item_dict = task_details.get('item_dict')
        task_type = task_details.get('task_type')
        item_id = task_details.get('item_id')

        if not all([task_id, args_obj, item_dict, task_type, item_id]):
             self._update_task_status(task_id, "Error", "Missing task details for execution.")
             return

        self._update_task_status(task_id, "Running")
        saved_output_file = None
        try:
            if not isinstance(args_obj, ArgsNamespace):
                 logger.error(f"Task {task_id}: args_obj is not ArgsNamespace type. Recreating.")
                 args_obj = ArgsNamespace(
                      data_dir=DATA_DIR, results_dir=RESULTS_DIR,
                      species=task_details.get('species'), model=task_details.get('model'),
                      reasoning_level=task_details.get('depth'),
                      bench_file=BENCHMARKS_FILE, scenarios_file=SCENARIOS_FILE
                 )

            logger.info(f"Executing Task {task_id}: Single {task_type} ID {item_id}")

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
             logger.error(f"Runtime Error executing task {task_id}: {e}\n{traceback.format_exc()}")

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
            logger.info(f"Executing Task {task_id}: All Scenarios")
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
             logger.error(f"Runtime Error executing task {task_id} (all scenarios): {e}\n{traceback.format_exc()}")

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
            logger.info(f"Executing Task {task_id}: All Benchmarks")
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
             logger.error(f"Runtime Error executing task {task_id} (all benchmarks): {e}\n{traceback.format_exc()}")


    async def action_start_queue(self):
        """Processes the tasks in the app's queue sequentially."""
        if self.app.is_queue_processing:
            self.app.notify("Queue is already processing.", severity="warning")
            return
        if not self.app.task_queue:
            self.app.notify("Queue is empty.", severity="info")
            return

        self.app.is_queue_processing = True
        self.app.loading = True
        self.app.run_status = "Processing Queue..."
        logger.info("Starting queue processing...")

        queue_to_process = list(self.app.task_queue)

        for task in queue_to_process:
            if task.get('status') in ['Completed', 'Error', 'Warning']:
                 logger.debug(f"Skipping task {task.get('id')} with status {task.get('status')}")
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
                    logger.error(f"Unknown task type '{task_type}' for task ID {task_id}")


            except Exception as e:
                error_msg = f"Queue processing error: {e}"
                if task_id:
                    self._update_task_status(task_id, "Error", error_msg)
                logger.error(f"Error during queue processing loop for task {task_id}: {e}", exc_info=True)

        self.app.is_queue_processing = False
        self.app.loading = False
        self.app.run_status = "Queue Processing Finished"
        logger.info("Queue processing finished.")
        self.app.notify("Finished processing all tasks in the queue.", title="Queue Complete")

        current_queue = list(self.app.task_queue)
        filtered_queue = [
            task for task in current_queue
            if task.get('status') not in ['Completed', 'Error']
        ]
        if len(filtered_queue) != len(current_queue):
            self.app.task_queue = filtered_queue
            logger.info(f"Filtered queue: Removed {len(current_queue) - len(filtered_queue)} completed/errored tasks.")
        else:
            logger.info("Queue filtering: No completed/errored tasks found to remove.")


        try:
            from .views.results_browser_view import ResultsBrowserView
            browser_view = self.app.query_one(ResultsBrowserView)
            browser_view._populate_file_list()
            logger.info("Results browser refreshed after queue completion.")
        except Exception as browse_e:
            self.app.log.warning(f"Could not refresh browser list after queue: {browse_e}")

    def action_clear_queue(self):
        """Clears all tasks from the app's queue."""
        if self.app.is_queue_processing:
            self.app.notify("Cannot clear queue while it's processing.", severity="warning")
            return

        if not self.app.task_queue:
            self.app.notify("Queue is already empty.", severity="info")
            return

        self.app.task_queue = []
        logger.info("Task queue cleared.")
        self.app.notify("Queue cleared.", title="Queue Cleared")

    def add_task_to_queue(self, task_details: dict):
        """Adds a validated task dictionary to the app's queue."""
        if 'id' not in task_details:
            task_details['id'] = str(uuid.uuid4())
        if 'status' not in task_details:
            task_details['status'] = 'Pending'

        self.app.task_queue = self.app.task_queue + [task_details]
        logger.info(f"Added task {task_details.get('id')} to queue.")
