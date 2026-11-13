import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from components.sidebar import header  # noqa: E402
from components.task_monitor import preset_form  # noqa: E402

header("Code Assistant", "Generate, explain and debug Python. Attach a .py file to debug it.")
preset_form("code_task", "Describe the code you need (or paste code to debug)", "e.g. Write a function that validates email addresses, with tests",
            ["coder"], ["py", "txt", "md", "json"], button="💻 Generate")
