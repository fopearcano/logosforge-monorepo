"""Example plugin for Logosforge."""


def register(api):
    api.log("Example plugin loaded.")

    def greet():
        title = api.get_project_title()
        count = api.get_scene_count()
        api.show_message(
            "Hello from Plugin",
            f"Project: {title}\nScenes: {count}",
        )

    api.register_menu_action("Hello from Plugin", greet)
