import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from components.sidebar import header  # noqa: E402
from components.task_monitor import preset_form  # noqa: E402

header("Data Analysis", "Upload a CSV/Excel file - Pandas profiling, Plotly charts and an analytical summary.")
preset_form("data_task", "What would you like to know?", "e.g. Find missing values, summarise revenue by region and show the key trends",
            ["data_analyst", "writer"], ["csv", "xlsx", "xls"], button="📊 Analyse")
