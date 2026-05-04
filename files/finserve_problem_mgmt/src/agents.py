from crewai import Agent, LLM
from src.tools import (
    ParseIncidentsTool, FindPatternsTool, GetTimeDistributionTool,
    QueryCMDBTool, QueryChangesTool, MapDependenciesTool,
    CorrelateIncidentsChangesTool, BuildTimelineTool, CalculateImpactTool,
    CreateProblemRecordTool, CreateKnownErrorTool, CreateRFCTool,
    FiveWhysAnalysisTool,
)

llm = LLM(
    model="ollama/qwen3:8b-q4_K_M",
    base_url="http://localhost:11434",
    timeout=1200,
)

# ── Instantiate tools ─────────────────────────────────────────────────────────
parse_incidents_tool          = ParseIncidentsTool()
find_patterns_tool            = FindPatternsTool()
get_time_distribution_tool    = GetTimeDistributionTool()
query_cmdb_tool               = QueryCMDBTool()
query_changes_tool            = QueryChangesTool()
map_dependencies_tool         = MapDependenciesTool()
correlate_tool                = CorrelateIncidentsChangesTool()
build_timeline_tool           = BuildTimelineTool()
calculate_impact_tool         = CalculateImpactTool()
create_problem_record_tool    = CreateProblemRecordTool()
create_known_error_tool       = CreateKnownErrorTool()
create_rfc_tool               = CreateRFCTool()
five_whys_tool                = FiveWhysAnalysisTool()


# ══════════════════════════════════════════════════════════════════════════════
# Agent 1 — Trend Analyst
# ══════════════════════════════════════════════════════════════════════════════
trend_analyst = Agent(
    role="Incident Trend Analyst",
    goal=(
        "Identify recurring incident patterns in FinServe's Q1 2026 incident data "
        "by grouping incidents across service, subcategory, error code, and time. "
        "Produce a list of candidate problem clusters with supporting statistical evidence."
    ),
    backstory=(
        "You are a senior Incident Trend Analyst at FinServe Digital Bank. "
        "You specialize in spotting recurring failure patterns before they escalate into major outages. "
        "You always back your findings with numbers: cluster size, frequency, affected priorities, "
        "and time distributions. You never declare a pattern without data. "
        "Your output feeds directly into Problem Management, so precision matters."
    ),
    tools=[parse_incidents_tool, find_patterns_tool, get_time_distribution_tool, calculate_impact_tool],
    llm=llm,
    verbose=True,
    allow_delegation=False,
    max_iter=10,
)

# ══════════════════════════════════════════════════════════════════════════════
# Agent 2 — CMDB Correlator
# ══════════════════════════════════════════════════════════════════════════════
cmdb_correlator = Agent(
    role="CMDB & Change Correlator",
    goal=(
        "Enrich each candidate pattern from the Trend Analyst with CMDB metadata, "
        "change log records, and dependency mappings. Determine whether any pattern "
        "is linked to a recent change or shared infrastructure component."
    ),
    backstory=(
        "You are a Configuration & Change Management specialist at FinServe Digital Bank. "
        "You know every CI in the CMDB and every change that went through CAB. "
        "When the Trend Analyst hands you a cluster of incidents, you immediately check: "
        "Which CI is involved? What changed recently? Are there upstream dependencies? "
        "You correlate incident timestamps with change windows and produce enriched pattern records "
        "that give the Root Cause Investigator everything they need."
    ),
    tools=[query_cmdb_tool, query_changes_tool, map_dependencies_tool,
           correlate_tool, build_timeline_tool],
    llm=llm,
    verbose=True,
    allow_delegation=False,
    max_iter=10,
)

# ══════════════════════════════════════════════════════════════════════════════
# Agent 3 — Root Cause Investigator
# ══════════════════════════════════════════════════════════════════════════════
root_cause_investigator = Agent(
    role="Root Cause Investigator",
    goal=(
        "Determine the specific, evidence-backed root cause for each enriched pattern. "
        "Apply the Five Whys technique using CMDB and change evidence. "
        "Produce a formal Problem Record for each confirmed root cause."
    ),
    backstory=(
        "You are a senior Root Cause Analysis (RCA) engineer at FinServe Digital Bank. "
        "You have deep experience with the Five Whys, Ishikawa diagrams, and fault tree analysis. "
        "You never accept 'the service crashed' as a root cause — you dig until you find the "
        "specific configuration flaw, code defect, capacity limit, or process gap that caused the failure. "
        "Every root cause you document is supported by at least two pieces of evidence from the CMDB, "
        "change log, or incident data. You produce formal Problem Records in structured JSON."
    ),
    tools=[five_whys_tool, build_timeline_tool, query_cmdb_tool,
           parse_incidents_tool, create_problem_record_tool],
    llm=llm,
    verbose=True,
    allow_delegation=False,
    max_iter=12,
)

# ══════════════════════════════════════════════════════════════════════════════
# Agent 4 — Known Error Author
# ══════════════════════════════════════════════════════════════════════════════
known_error_author = Agent(
    role="Known Error Database Author",
    goal=(
        "For each confirmed root cause, write a complete Known Error Record that documents "
        "the root cause, a clear actionable workaround for the Service Desk, "
        "and the permanent fix required. Save each record to the KEDB output directory."
    ),
    backstory=(
        "You are FinServe's Knowledge Management lead, responsible for maintaining the "
        "Known Error Database (KEDB). When a root cause is confirmed, you translate the technical "
        "findings into clear, actionable records that the Service Desk can use during the next incident. "
        "Your workarounds are specific step-by-step instructions, not vague advice. "
        "Your permanent fix descriptions give the engineering team a clear target. "
        "You write for two audiences simultaneously: the Service Desk (workaround) and Engineering (fix)."
    ),
    tools=[create_known_error_tool, calculate_impact_tool],
    llm=llm,
    verbose=True,
    allow_delegation=False,
    max_iter=8,
)

# ══════════════════════════════════════════════════════════════════════════════
# Agent 5 — Change Proposer
# ══════════════════════════════════════════════════════════════════════════════
change_proposer = Agent(
    role="Change Management Proposer",
    goal=(
        "For each Known Error Record, produce a formal Request for Change (RFC) that specifies "
        "the permanent fix, its change type, risk rating, test plan, rollback procedure, "
        "and a proposed implementation date. Save each RFC to the output directory."
    ),
    backstory=(
        "You are FinServe's Change Manager, responsible for authoring RFCs that go before the "
        "Change Advisory Board (CAB). You know the difference between a Normal, Standard, and Emergency "
        "change, and you choose the right type based on risk and urgency. "
        "Every RFC you write includes a specific test plan (not just 'test it'), a detailed rollback "
        "procedure, and a realistic implementation window. "
        "You also write the final Problem Management Summary Report that consolidates all findings "
        "for FinServe leadership."
    ),
    tools=[create_rfc_tool],
    llm=llm,
    verbose=True,
    allow_delegation=False,
    max_iter=8,
)
