# dashboard_actions.py
import os
import json
import asyncio
from data_manager import save_json

def refresh_view(app):
    """Clear and repopulate the dynamic main container based on the current tab."""
    main_container = app.query_one("#main_container")
    for child in list(main_container.children):
        child.remove()

    if app.current_tab == "Scenarios":
        from dashboard_views import ScenariosView
        main_container.mount(ScenariosView(app.scenarios))
    elif app.current_tab == "Models":
        from dashboard_views import ModelsView
        main_container.mount(ModelsView(app.models))
    elif app.current_tab == "Species":
        from textual.widgets import ListView, ListItem, Label
        list_view = ListView(
            *[ListItem(Label(f"{name}: {desc[:50]}...")) for name, desc in app.species.items()],
            id="species_list"
        )
        from textual.containers import Container
        main_container.mount(Container(list_view))
    elif app.current_tab == "Summarizers":
        from dashboard_views import SummarizersView
        main_container.mount(SummarizersView(app.summarizers))
    elif app.current_tab == "Runs":
        from dashboard_views import RunsView
        main_container.mount(RunsView())

def run_analysis_action(app):
    """Offload the analysis to a background thread and update the app’s status and results."""
    async def inner():
        app.run_status = "Running..."
        app.query_one("#run_status").update(f"Status: {app.run_status}")
        try:
            from main import run_analysis_for_dashboard
            app.analysis_results = await asyncio.to_thread(
                run_analysis_for_dashboard,
                scenarios=app.scenarios,
                reasoning_models=app.models,
                summarizer_prompts=app.summarizers
            )
            last_line = ""
            for line in reversed(app.analysis_results.strip().splitlines()):
                if line.strip():
                    last_line = line.strip()
                    break
            app.run_status = last_line if last_line else "Completed"
            app.query_one("#run_status").update(f"Status: {app.run_status}")
            update_results_table(app)
        except Exception as e:
            app.run_status = f"Error: {str(e)}"
            app.query_one("#run_status").update(f"Status: {app.run_status}")
    asyncio.create_task(inner())

def update_results_table(app):
    """Update the results table from the results file."""
    results_table = app.query_one("#run_results_table")
    results_table.clear()
    results_path = os.path.join("results", "results.json")
    if os.path.exists(results_path):
        with open(results_path, "r") as f:
            data = json.load(f)
        summary = data.get("summary", "")
        results_table.add_row("Summary", "", summary)
    else:
        results_table.add_row("Summary", "", app.analysis_results.strip().replace("\n", "<br>"))

def action_create(app, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, SUMMARIZERS_FILE):
    if app.current_tab == "Scenarios":
        new_name = f"New Scenario {len(app.scenarios) + 1}"
        app.scenarios[new_name] = f"Description for {new_name}"
        save_json(SCENARIOS_FILE, app.scenarios)
    elif app.current_tab == "Models":
        new_name = f"New Model {len(app.models) + 1}"
        app.models[new_name] = f"Description for {new_name}"
        save_json(GOLDEN_PATTERNS_FILE, app.models)
    elif app.current_tab == "Species":
        new_name = f"New Species {len(app.species) + 1}"
        app.species[new_name] = f"Traits for {new_name}"
        save_json(SPECIES_FILE, app.species)
    elif app.current_tab == "Summarizers":
        new_name = f"New Summarizer {len(app.summarizers) + 1}"
        app.summarizers[new_name] = f"Prompt for {new_name}"
        save_json(SUMMARIZERS_FILE, app.summarizers)
    refresh_view(app)

def launch_edit(app, list_selector, data, file_path):
    list_view = app.query_one(list_selector)
    selected_index = list_view.index
    if selected_index is None or selected_index < 0 or selected_index >= len(data):
        return
    key = list(data.keys())[selected_index]
    from textual.widgets import Input
    input_widget = Input(name="edit_input", placeholder="Edit item text…", value=data[key])
    app.editing_item = (data, file_path, key)
    list_view.parent.mount(input_widget, before=list_view)
    input_widget.focus()

def action_edit(app, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, SUMMARIZERS_FILE):
    if app.current_tab == "Scenarios":
        launch_edit(app, "#scenarios_list", app.scenarios, SCENARIOS_FILE)
    elif app.current_tab == "Models":
        launch_edit(app, "#models_list", app.models, GOLDEN_PATTERNS_FILE)
    elif app.current_tab == "Species":
        launch_edit(app, "#species_list", app.species, SPECIES_FILE)
    elif app.current_tab == "Summarizers":
        launch_edit(app, "#summarizers_list", app.summarizers, SUMMARIZERS_FILE)

def action_delete(app, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, SUMMARIZERS_FILE):
    list_view = None
    data = None
    file_path = None
    if app.current_tab == "Scenarios":
        list_view = app.query_one("#scenarios_list")
        data = app.scenarios
        file_path = SCENARIOS_FILE
    elif app.current_tab == "Models":
        list_view = app.query_one("#models_list")
        data = app.models
        file_path = GOLDEN_PATTERNS_FILE
    elif app.current_tab == "Species":
        list_view = app.query_one("#species_list")
        data = app.species
        file_path = SPECIES_FILE
    elif app.current_tab == "Summarizers":
        list_view = app.query_one("#summarizers_list")
        data = app.summarizers
        file_path = SUMMARIZERS_FILE

    if list_view and data:
        try:
            selected_index = list_view.index
            key = list(data.keys())[selected_index]
            del data[key]
            save_json(file_path, data)
            refresh_view(app)
        except Exception:
            pass
