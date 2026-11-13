import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from components.sidebar import header  # noqa: E402
from components.task_monitor import preset_form  # noqa: E402

header("Document Generator", "Reports, emails, summaries and meeting minutes. Mention PDF or Word to get a downloadable file.")
preset_form("doc_task", "What should the document contain?", "e.g. Write a PDF report on remote-work productivity with an executive summary and recommendations",
            ["writer"], ["txt", "md", "docx", "pdf", "csv"], button="📄 Generate document")
