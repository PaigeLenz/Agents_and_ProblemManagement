import os
import json
import pandas as pd
from datetime import datetime, timedelta
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional

# ── Paths (set via env or fall back to data/) ─────────────────────────────────
INCIDENTS_PATH = os.getenv("INCIDENTS_CSV", "data/finserve_incidents_q1_2026.csv")
CMDB_PATH      = os.getenv("CMDB_CSV",      "data/finserve_cmdb.csv")
CHANGES_PATH   = os.getenv("CHANGES_CSV",   "data/finserve_changes.csv")
OUTPUT_DIR     = os.getenv("OUTPUT_DIR",    "output")

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 1 — ParseIncidents
# ══════════════════════════════════════════════════════════════════════════════
class ParseIncidentsInput(BaseModel):
    service: Optional[str]    = Field(None, description="Filter by service name (partial match OK)")
    priority: Optional[str]   = Field(None, description="Filter by priority, e.g. 'P1-Critical'")
    error_code: Optional[str] = Field(None, description="Filter by error code, e.g. 'ERR-5012'")
    start_date: Optional[str] = Field(None, description="Filter incidents on/after YYYY-MM-DD")
    end_date: Optional[str]   = Field(None, description="Filter incidents on/before YYYY-MM-DD")
    max_rows: int             = Field(50, description="Maximum rows to return (default 50)")

class ParseIncidentsTool(BaseTool):
    name: str        = "parse_incidents"
    description: str = "Read the incident CSV and return structured records, optionally filtered."
    args_schema: type[BaseModel] = ParseIncidentsInput

    def _run(self, service=None, priority=None, error_code=None,
             start_date=None, end_date=None, max_rows=50) -> str:
        df = pd.read_csv(INCIDENTS_PATH)
        df["opened_at"] = pd.to_datetime(df["opened_at"], errors="coerce")
        if service:
            df = df[df["service"].str.contains(service, case=False, na=False)]
        if priority:
            df = df[df["priority"].str.contains(priority, case=False, na=False)]
        if error_code:
            df = df[df["error_code"].str.contains(error_code, case=False, na=False)]
        if start_date:
            df = df[df["opened_at"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["opened_at"] <= pd.to_datetime(end_date)]
        result = df.head(max_rows).to_dict(orient="records")
        return json.dumps(result, default=str)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 2 — FindPatterns
# ══════════════════════════════════════════════════════════════════════════════
class FindPatternsInput(BaseModel):
    min_count: int = Field(3, description="Minimum incidents in a cluster to be reported")
    group_by: str  = Field(
        "service,subcategory,error_code",
        description="Comma-separated columns to group by"
    )

class FindPatternsTool(BaseTool):
    name: str        = "find_patterns"
    description: str = "Group incidents by configurable columns and return clusters above a threshold."
    args_schema: type[BaseModel] = FindPatternsInput

    def _run(self, min_count=3, group_by="service,subcategory,error_code") -> str:
        df = pd.read_csv(INCIDENTS_PATH)
        cols = [c.strip() for c in group_by.split(",") if c.strip() in df.columns]
        if not cols:
            return json.dumps({"error": f"None of {group_by} found in CSV columns: {list(df.columns)}"})
        grouped = df.groupby(cols, dropna=False).agg(
            count=("incident_id", "count"),
            incidents=("incident_id", list),
            priorities=("priority", lambda x: x.value_counts().to_dict()),
            sample_description=("short_description", "first"),
        ).reset_index()
        clusters = grouped[grouped["count"] >= min_count].sort_values("count", ascending=False)
        return clusters.to_json(orient="records")


# ══════════════════════════════════════════════════════════════════════════════
# Tool 3 — GetTimeDistribution
# ══════════════════════════════════════════════════════════════════════════════
class TimeDistInput(BaseModel):
    incident_ids: str = Field(..., description="Comma-separated list of incident IDs to analyze")

class GetTimeDistributionTool(BaseTool):
    name: str        = "get_time_distribution"
    description: str = "Return day-of-week and hour-of-day breakdown for a set of incident IDs."
    args_schema: type[BaseModel] = TimeDistInput

    def _run(self, incident_ids: str) -> str:
        df = pd.read_csv(INCIDENTS_PATH)
        ids = [i.strip() for i in incident_ids.split(",")]
        subset = df[df["incident_id"].isin(ids)].copy()
        subset["opened_at"] = pd.to_datetime(subset["opened_at"], errors="coerce")
        subset["day_of_week"] = subset["opened_at"].dt.day_name()
        subset["hour"] = subset["opened_at"].dt.hour
        return json.dumps({
            "day_of_week": subset["day_of_week"].value_counts().to_dict(),
            "hour_of_day": subset["hour"].value_counts().sort_index().to_dict(),
            "total_incidents": len(subset),
        })


# ══════════════════════════════════════════════════════════════════════════════
# Tool 4 — QueryCMDB
# ══════════════════════════════════════════════════════════════════════════════
class QueryCMDBInput(BaseModel):
    ci_id: str = Field(..., description="The Configuration Item ID to look up, e.g. CI-001")

class QueryCMDBTool(BaseTool):
    name: str        = "query_cmdb"
    description: str = "Look up a CI by ID and return its full CMDB record including dependencies."
    args_schema: type[BaseModel] = QueryCMDBInput

    def _run(self, ci_id: str) -> str:
        df = pd.read_csv(CMDB_PATH)
        # Try matching on common ID column names
        for col in ["ci_id", "id", "CI_ID", "ID"]:
            if col in df.columns:
                match = df[df[col].astype(str).str.upper() == ci_id.upper()]
                if not match.empty:
                    return match.to_json(orient="records")
        return json.dumps({"error": f"CI '{ci_id}' not found. Available columns: {list(df.columns)}"})


# ══════════════════════════════════════════════════════════════════════════════
# Tool 5 — QueryChanges
# ══════════════════════════════════════════════════════════════════════════════
class QueryChangesInput(BaseModel):
    ci_id: Optional[str]      = Field(None, description="Filter changes for this CI ID")
    start_date: Optional[str] = Field(None, description="Changes on/after YYYY-MM-DD")
    end_date: Optional[str]   = Field(None, description="Changes on/before YYYY-MM-DD")

class QueryChangesTool(BaseTool):
    name: str        = "query_changes"
    description: str = "Return change records from the change log, optionally filtered by CI or date."
    args_schema: type[BaseModel] = QueryChangesInput

    def _run(self, ci_id=None, start_date=None, end_date=None) -> str:
        df = pd.read_csv(CHANGES_PATH)
        # Detect date column
        date_col = next((c for c in df.columns if "date" in c.lower() or "implement" in c.lower()), None)
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        if ci_id:
            ci_col = next((c for c in df.columns if "ci" in c.lower()), None)
            if ci_col:
                df = df[df[ci_col].astype(str).str.contains(ci_id, case=False, na=False)]
        if start_date and date_col:
            df = df[df[date_col] >= pd.to_datetime(start_date)]
        if end_date and date_col:
            df = df[df[date_col] <= pd.to_datetime(end_date)]
        return df.to_json(orient="records", default_handler=str)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 6 — MapDependencies
# ══════════════════════════════════════════════════════════════════════════════
class MapDepsInput(BaseModel):
    ci_id: str = Field(..., description="Starting CI to map dependencies from")

class MapDependenciesTool(BaseTool):
    name: str        = "map_dependencies"
    description: str = "Walk the CMDB dependency graph and return upstream/downstream CIs."
    args_schema: type[BaseModel] = MapDepsInput

    def _run(self, ci_id: str) -> str:
        df = pd.read_csv(CMDB_PATH)
        dep_col = next((c for c in df.columns if "depend" in c.lower()), None)
        id_col  = next((c for c in df.columns if "ci_id" in c.lower() or c.lower() == "id"), None)
        if not dep_col or not id_col:
            return json.dumps({"error": "Could not find dependency or ID column in CMDB."})
        row = df[df[id_col].astype(str).str.upper() == ci_id.upper()]
        if row.empty:
            return json.dumps({"error": f"CI {ci_id} not found."})
        deps_raw = str(row.iloc[0][dep_col])
        # Find CIs that depend on this CI (downstream)
        downstream = df[df[dep_col].astype(str).str.contains(ci_id, case=False, na=False)][id_col].tolist()
        return json.dumps({
            "ci_id": ci_id,
            "upstream_dependencies": [d.strip() for d in deps_raw.split(",") if d.strip() and d.strip().lower() != "nan"],
            "downstream_dependents": downstream,
        })


# ══════════════════════════════════════════════════════════════════════════════
# Tool 7 — CorrelateIncidentsChanges
# ══════════════════════════════════════════════════════════════════════════════
class CorrelateInput(BaseModel):
    incident_ids: str = Field(..., description="Comma-separated list of incident IDs")
    window_days: int  = Field(7, description="Look back this many days before each incident for changes")

class CorrelateIncidentsChangesTool(BaseTool):
    name: str        = "correlate_incidents_changes"
    description: str = "For each incident, find changes implemented within a window before it."
    args_schema: type[BaseModel] = CorrelateInput

    def _run(self, incident_ids: str, window_days: int = 7) -> str:
        inc_df = pd.read_csv(INCIDENTS_PATH)
        chg_df = pd.read_csv(CHANGES_PATH)
        ids = [i.strip() for i in incident_ids.split(",")]
        inc_df["opened_at"] = pd.to_datetime(inc_df["opened_at"], errors="coerce")
        date_col = next((c for c in chg_df.columns if "date" in c.lower() or "implement" in c.lower()), None)
        if date_col:
            chg_df[date_col] = pd.to_datetime(chg_df[date_col], errors="coerce")
        correlations = []
        for iid in ids:
            row = inc_df[inc_df["incident_id"] == iid]
            if row.empty:
                continue
            opened = row.iloc[0]["opened_at"]
            if pd.isnull(opened):
                continue
            window_start = opened - timedelta(days=window_days)
            if date_col:
                matching = chg_df[(chg_df[date_col] >= window_start) & (chg_df[date_col] <= opened)]
            else:
                matching = chg_df
            correlations.append({
                "incident_id": iid,
                "opened_at": str(opened),
                "changes_in_window": matching.to_dict(orient="records"),
            })
        return json.dumps(correlations, default=str)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 8 — BuildTimeline
# ══════════════════════════════════════════════════════════════════════════════
class TimelineInput(BaseModel):
    ci_id: Optional[str]      = Field(None, description="CI to build timeline for")
    service: Optional[str]    = Field(None, description="Service name to filter incidents")
    start_date: Optional[str] = Field(None, description="YYYY-MM-DD start of timeline")
    end_date: Optional[str]   = Field(None, description="YYYY-MM-DD end of timeline")

class BuildTimelineTool(BaseTool):
    name: str        = "build_timeline"
    description: str = "Build a merged chronological timeline of incidents + changes for a CI/service."
    args_schema: type[BaseModel] = TimelineInput

    def _run(self, ci_id=None, service=None, start_date=None, end_date=None) -> str:
        inc_df = pd.read_csv(INCIDENTS_PATH)
        chg_df = pd.read_csv(CHANGES_PATH)
        inc_df["opened_at"] = pd.to_datetime(inc_df["opened_at"], errors="coerce")
        date_col = next((c for c in chg_df.columns if "date" in c.lower() or "implement" in c.lower()), None)
        if date_col:
            chg_df[date_col] = pd.to_datetime(chg_df[date_col], errors="coerce")
        if service:
            inc_df = inc_df[inc_df["service"].str.contains(service, case=False, na=False)]
        if ci_id and "ci_id" in inc_df.columns:
            inc_df = inc_df[inc_df["ci_id"].astype(str).str.upper() == ci_id.upper()]
        if start_date:
            inc_df = inc_df[inc_df["opened_at"] >= pd.to_datetime(start_date)]
        if end_date:
            inc_df = inc_df[inc_df["opened_at"] <= pd.to_datetime(end_date)]
        events = []
        for _, r in inc_df.iterrows():
            events.append({"timestamp": str(r["opened_at"]), "type": "INCIDENT",
                           "id": r["incident_id"], "detail": r.get("short_description", "")})
        if date_col:
            for _, r in chg_df.iterrows():
                events.append({"timestamp": str(r[date_col]), "type": "CHANGE",
                               "id": r.get("change_id", r.get("id", "?")), "detail": r.get("title", "")})
        events.sort(key=lambda x: x["timestamp"])
        return json.dumps(events, default=str)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 9 — CalculateImpact
# ══════════════════════════════════════════════════════════════════════════════
class ImpactInput(BaseModel):
    incident_ids: str = Field(..., description="Comma-separated incident IDs to calculate impact for")

class CalculateImpactTool(BaseTool):
    name: str        = "calculate_impact"
    description: str = "Compute total incidents, downtime hours, and priority breakdown for a set of IDs."
    args_schema: type[BaseModel] = ImpactInput

    def _run(self, incident_ids: str) -> str:
        df = pd.read_csv(INCIDENTS_PATH)
        ids = [i.strip() for i in incident_ids.split(",")]
        subset = df[df["incident_id"].isin(ids)].copy()
        subset["opened_at"]   = pd.to_datetime(subset["opened_at"], errors="coerce")
        subset["resolved_at"] = pd.to_datetime(subset["resolved_at"], errors="coerce")
        subset["duration_h"]  = (subset["resolved_at"] - subset["opened_at"]).dt.total_seconds() / 3600
        return json.dumps({
            "total_incidents": len(subset),
            "total_downtime_hours": round(subset["duration_h"].sum(), 2),
            "avg_duration_hours": round(subset["duration_h"].mean(), 2),
            "priority_breakdown": subset["priority"].value_counts().to_dict(),
            "services_affected": subset["service"].unique().tolist(),
        })


# ══════════════════════════════════════════════════════════════════════════════
# Tool 10 — CreateProblemRecord
# ══════════════════════════════════════════════════════════════════════════════
class ProblemRecordInput(BaseModel):
    pattern_id: str      = Field(..., description="Short identifier like PROB-001")
    title: str           = Field(..., description="One-line description of the problem")
    severity: str        = Field(..., description="Critical / High / Medium / Low")
    affected_cis: str    = Field(..., description="Comma-separated CI IDs")
    linked_incidents: str= Field(..., description="Comma-separated incident IDs")
    description: str     = Field(..., description="Narrative describing the pattern observed")

class CreateProblemRecordTool(BaseTool):
    name: str        = "create_problem_record"
    description: str = "Generate and save a formal Problem Record as a JSON file."
    args_schema: type[BaseModel] = ProblemRecordInput

    def _run(self, pattern_id, title, severity, affected_cis, linked_incidents, description) -> str:
        record = {
            "problem_id": pattern_id,
            "title": title,
            "status": "Under Investigation",
            "severity": severity,
            "affected_cis": [c.strip() for c in affected_cis.split(",")],
            "linked_incidents": [i.strip() for i in linked_incidents.split(",")],
            "description": description,
            "created_at": datetime.now().isoformat(),
        }
        path = os.path.join(OUTPUT_DIR, f"{pattern_id}_problem_record.json")
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        return json.dumps({"status": "saved", "path": path, "record": record})


# ══════════════════════════════════════════════════════════════════════════════
# Tool 11 — CreateKnownError (WRITES FILE)
# ══════════════════════════════════════════════════════════════════════════════
class KnownErrorInput(BaseModel):
    ke_id: str           = Field(..., description="Known Error ID, e.g. KE-001")
    problem_id: str      = Field(..., description="Linked problem record ID")
    root_cause: str      = Field(..., description="Confirmed root cause statement")
    workaround: str      = Field(..., description="Steps the Service Desk can use to resolve future incidents faster")
    permanent_fix: str   = Field(..., description="Description of the permanent resolution required")
    affected_ci: str     = Field(..., description="Primary CI affected")
    linked_incidents: str= Field(..., description="Comma-separated incident IDs")

class CreateKnownErrorTool(BaseTool):
    name: str        = "create_known_error"
    description: str = "Produce a Known Error Record and save it to the output directory."
    args_schema: type[BaseModel] = KnownErrorInput

    def _run(self, ke_id, problem_id, root_cause, workaround, permanent_fix, affected_ci, linked_incidents) -> str:
        record = {
            "ke_id": ke_id,
            "problem_id": problem_id,
            "status": "Known Error",
            "root_cause": root_cause,
            "workaround": workaround,
            "permanent_fix": permanent_fix,
            "affected_ci": affected_ci,
            "linked_incidents": [i.strip() for i in linked_incidents.split(",")],
            "created_at": datetime.now().isoformat(),
        }
        path = os.path.join(OUTPUT_DIR, f"{ke_id}_known_error.json")
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        return json.dumps({"status": "saved", "path": path, "record": record})


# ══════════════════════════════════════════════════════════════════════════════
# Tool 12 — CreateRFC (WRITES FILE)
# ══════════════════════════════════════════════════════════════════════════════
class RFCInput(BaseModel):
    rfc_id: str         = Field(..., description="RFC ID, e.g. RFC-001")
    ke_id: str          = Field(..., description="Linked Known Error ID")
    title: str          = Field(..., description="Short title of the proposed change")
    description: str    = Field(..., description="Full description of what will be changed")
    change_type: str    = Field(..., description="Normal / Standard / Emergency")
    risk_rating: str    = Field(..., description="Low / Medium / High")
    test_plan: str      = Field(..., description="How the change will be tested before deployment")
    rollback_plan: str  = Field(..., description="Steps to revert if the change fails")
    implementation_date: str = Field(..., description="Planned implementation date YYYY-MM-DD")

class CreateRFCTool(BaseTool):
    name: str        = "create_rfc"
    description: str = "Generate a Request for Change and save it to the output directory."
    args_schema: type[BaseModel] = RFCInput

    def _run(self, rfc_id, ke_id, title, description, change_type, risk_rating,
             test_plan, rollback_plan, implementation_date) -> str:
        record = {
            "rfc_id": rfc_id,
            "ke_id": ke_id,
            "title": title,
            "description": description,
            "change_type": change_type,
            "risk_rating": risk_rating,
            "test_plan": test_plan,
            "rollback_plan": rollback_plan,
            "planned_implementation": implementation_date,
            "status": "Proposed",
            "created_at": datetime.now().isoformat(),
        }
        path = os.path.join(OUTPUT_DIR, f"{rfc_id}_rfc.json")
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        return json.dumps({"status": "saved", "path": path, "record": record})


# ══════════════════════════════════════════════════════════════════════════════
# Tool 13 — FiveWhysAnalysis
# ══════════════════════════════════════════════════════════════════════════════
class FiveWhysInput(BaseModel):
    pattern_summary: str = Field(..., description="Brief summary of the pattern (service, error, frequency)")
    cmdb_info: str       = Field(..., description="Relevant CMDB data for this CI as a JSON string or text")
    change_info: str     = Field(..., description="Relevant changes that correlate with this pattern")

class FiveWhysAnalysisTool(BaseTool):
    name: str        = "five_whys_analysis"
    description: str = "Perform a structured Five Whys root cause analysis given pattern and context data."
    args_schema: type[BaseModel] = FiveWhysInput

    def _run(self, pattern_summary: str, cmdb_info: str, change_info: str) -> str:
        # This tool structures the inputs so the agent can reason through the Five Whys chain
        return json.dumps({
            "instruction": (
                "Using the information below, reason through the Five Whys technique. "
                "For each 'why', state the answer and what evidence supports it. "
                "Conclude with a single root cause statement."
            ),
            "pattern_summary": pattern_summary,
            "cmdb_context": cmdb_info,
            "change_context": change_info,
            "template": [
                "Why 1: Why did the symptom occur? → [answer + evidence]",
                "Why 2: Why did that happen? → [answer + evidence]",
                "Why 3: Why did that happen? → [answer + evidence]",
                "Why 4: Why did that happen? → [answer + evidence]",
                "Why 5: Why did that happen? → [ROOT CAUSE]",
            ],
        })
