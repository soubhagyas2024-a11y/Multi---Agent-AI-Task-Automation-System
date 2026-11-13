"""Data Analysis Agent: Pandas profiling, Plotly charts, Gemini narrative."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px

from agents.agent_state import AgentError, AgentState, SubTask, build_context
from automation.file_automation import output_path
from integrations import gemini_client
from utils.helpers import truncate

NAME = "data_analyst"
SYSTEM = ("You are the Data Analysis Agent. You receive a statistical profile computed with Pandas. Explain what the data shows, "
          "data-quality problems (missing values, outliers), notable patterns and recommended next steps. Base every claim on the profile.")


def load_frame(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext == ".csv":
        try:
            return pd.read_csv(path)
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="latin-1")
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    raise AgentError(f"Unsupported data file type: {ext}")


def profile(df: pd.DataFrame) -> str:
    miss = df.isna().sum()
    lines = [f"Rows: {len(df)}, Columns: {df.shape[1]}", "Columns/dtypes: " + ", ".join(f"{c} ({t})" for c, t in df.dtypes.astype(str).items()),
             "Missing values: " + (", ".join(f"{c}={n}" for c, n in miss.items() if n) or "none"),
             f"Duplicate rows: {int(df.duplicated().sum())}"]
    num = df.select_dtypes("number")
    if not num.empty:
        lines.append("Numeric statistics:\n" + num.describe().round(3).to_string())
    for c in df.select_dtypes(exclude="number").columns[:4]:
        lines.append(f"Top values of {c}: " + ", ".join(f"{k}={v}" for k, v in df[c].value_counts().head(5).items()))
    return "\n".join(lines)


def make_charts(df: pd.DataFrame, state: AgentState, tag: str) -> list[dict]:
    figs = []
    num = list(df.select_dtypes("number").columns)
    cat = [c for c in df.select_dtypes(exclude="number").columns if 1 < df[c].nunique() <= 20]
    for c in num[:3]:
        figs.append((f"hist_{c}", px.histogram(df, x=c, title=f"Distribution of {c}", template="plotly_dark")))
    if len(num) >= 2:
        figs.append(("correlation", px.imshow(df[num].corr(), text_auto=".2f", title="Correlation matrix", template="plotly_dark")))
    if cat and num:
        g = df.groupby(cat[0])[num[0]].mean().reset_index()
        figs.append((f"{num[0]}_by_{cat[0]}", px.bar(g, x=cat[0], y=num[0], title=f"Mean {num[0]} by {cat[0]}", template="plotly_dark")))
    out = []
    for name, fig in figs:
        p = output_path(state["user_id"], f"chart_{tag}_{name}.html")
        fig.write_html(str(p), include_plotlyjs="cdn")
        out.append({"path": str(p), "type": "html"})
    return out


def run(state: AgentState, st: SubTask) -> dict:
    files = [f for f in state.get("files", []) if Path(f["path"]).suffix.lower() in (".csv", ".xlsx", ".xls")]
    if not files:
        raise AgentError("No CSV/Excel file was attached - upload a dataset first")
    try:
        df = load_frame(Path(files[0]["path"]))
    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AgentError(f"Could not read '{files[0]['filename']}': {exc}")
    if df.empty:
        raise AgentError("The dataset is empty")
    prof = profile(df)
    artifacts = make_charts(df, state, f"{state['task_id']}_{st['id']}")
    sp = output_path(state["user_id"], f"summary_stats_{state['task_id']}.csv")
    df.describe(include="all").to_csv(sp)
    artifacts.append({"path": str(sp), "type": "csv"})
    narrative = gemini_client.generate(f"{build_context(state, st)}\n\nQUESTION: {st['description']}\n\nPROFILE:\n{truncate(prof, 6000)}", system=SYSTEM)
    return {"output": f"### Dataset profile\n```\n{prof}\n```\n\n### Analysis\n{narrative}", "artifacts": artifacts}
