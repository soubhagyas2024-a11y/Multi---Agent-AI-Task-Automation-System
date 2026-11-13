import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from components.sidebar import header  # noqa: E402
from components.task_monitor import preset_form  # noqa: E402

header("Research Centre", "Web research via Tavily, synthesised by Gemini with numbered source references.")
preset_form("research_task", "Research question", "e.g. Compare the leading solid-state battery approaches and their commercial readiness",
            ["researcher", "writer"], button="🔎 Start research")
