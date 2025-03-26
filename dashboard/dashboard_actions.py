import os
import json
import asyncio


TAB_FILES = {
    "Scenarios": "data/scenarios.json",
    "Models": "data/golden_patterns.json",
    "Species": "data/species.json",
    "Judges": "data/judges.json"
}

def refresh_view(app):
    main_container = app.query_one("#main_container")
    # Remove all existing children
    for child in list(main_container.children):
        child.remove()

    from dashboard.dashboard_views import ScenariosView, ModelsView, JudgesView, RunsView

    if app.current_tab == "Scenarios":
        main_container.mount(ScenariosView(app.scenarios))
    elif app.current_tab == "Models":
        main_container.mount(ModelsView(app.models))
    elif app.current_tab == "Species":
        main_container.mount(ModelsView(app.species))
    elif app.current_tab == "Judges":
        main_container.mount(JudgesView(app.judges))
    elif app.current_tab == "Runs":
        main_container.mount(RunsView())

def run_analysis_action(app):
    async def inner():
        app.query_one("#run_status").update("Status: Running…")
        # Choose the first available species and scenario
        species = next(iter(app.species))
        scenario_key = next(iter(app.scenarios))
        scenario = {"id": scenario_key, "prompt": app.scenarios[scenario_key]}
        
        # Build a dummy args object to mimic parsed arguments.
        class DummyArgs:
            pass
        args_obj = DummyArgs()
        args_obj.data_dir = "data"
        args_obj.results_dir = "results"
        args_obj.species = species
        args_obj.model = next(iter(app.models))
        args_obj.reasoning_level = getattr(app, "reasoning_level", "low")
        
        # Import and use the new asynchronous pipeline function.
        from core.pipeline import run_pipeline_for_scenario
        record = await run_pipeline_for_scenario(scenario, args_obj)
        app.query_one("#run_status").update("Status: Completed")
        refresh_view(app)

    asyncio.create_task(inner())

def action_create(app):
    file_path = TAB_FILES[app.current_tab]
    data = getattr(app, app.current_tab.lower())
    key = f"New {app.current_tab[:-1]} {len(data) + 1}"
    data[key] = ""
    save_json(file_path, data)
    refresh_view(app)

def action_edit(app):
    file_path = TAB_FILES[app.current_tab]
    data = getattr(app, app.current_tab.lower())
    selected = app.get_selected_key()
    if selected:
        # For demonstration, update the selected item to a fixed placeholder.
        data[selected] = "Edited content"
        save_json(file_path, data)
        refresh_view(app)

def action_delete(app):
    file_path = TAB_FILES[app.current_tab]
    data = getattr(app, app.current_tab.lower())
    selected = app.get_selected_key()
    if selected:
        data.pop(selected, None)
        save_json(file_path, data)
        refresh_view(app)
