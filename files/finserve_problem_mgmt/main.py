from crewai import Agent, LLM
from src.tools import (
    ParseIncidentsTool, FindPatternsTool, GetTimeDistributionTool,
    QueryCMDBTool, QueryChangesTool, MapDependenciesTool,
    CorrelateIncidentsChangesTool, BuildTimelineTool, CalculateImpactTool,
    CreateProblemRecordTool, CreateKnownErrorTool, CreateRFCTool,
    FiveWhysAnalysisTool,
)

llm = LLM(
    model="ollama/qwen3:8b",
    base_url="http://localhost:11434",
    timeout=1200,
)
"""
FinServe Digital Bank — Agent-Driven Problem Management
Entry point: loads env vars, runs the crew, saves the final report.
"""

import os
import sys

# ── Set data file paths as env vars before importing tools ───────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.environ["INCIDENTS_CSV"] = os.path.join(BASE_DIR, "data", "finserve_incidents_q1_2026.csv")
os.environ["CMDB_CSV"]      = os.path.join(BASE_DIR, "data", "finserve_cmdb.csv")
os.environ["CHANGES_CSV"]   = os.path.join(BASE_DIR, "data", "finserve_changes.csv")
os.environ["OUTPUT_DIR"]    = os.path.join(BASE_DIR, "output")

# Verify the CSVs exist before starting
for env_var in ["INCIDENTS_CSV", "CMDB_CSV", "CHANGES_CSV"]:
    path = os.environ[env_var]
    if not os.path.isfile(path):
        print(f"ERROR: Could not find {env_var} at: {path}")
        print("Make sure all three CSV files are in the data/ folder.")
        sys.exit(1)

print("=" * 60)
print("FinServe Problem Management — Agent Crew Starting")
print("=" * 60)
print(f"  Incidents CSV : {os.environ['INCIDENTS_CSV']}")
print(f"  CMDB CSV      : {os.environ['CMDB_CSV']}")
print(f"  Changes CSV   : {os.environ['CHANGES_CSV']}")
print(f"  Output dir    : {os.environ['OUTPUT_DIR']}")
print("=" * 60)

from src.problem_crew import build_crew

crew   = build_crew()
result = crew.kickoff()

# ── Save the final Markdown report ───────────────────────────────────────────
report_path = os.path.join(os.environ["OUTPUT_DIR"], "problem_management_report.md")
os.makedirs(os.environ["OUTPUT_DIR"], exist_ok=True)

final_text = str(result)
with open(report_path, "w") as f:
    f.write(final_text)

print("\n" + "=" * 60)
print("CREW COMPLETE — Final Report")
print("=" * 60)
print(final_text)
print(f"\nReport saved to: {report_path}")
print("Check the output/ directory for Problem Records, Known Error Records, and RFCs.")
