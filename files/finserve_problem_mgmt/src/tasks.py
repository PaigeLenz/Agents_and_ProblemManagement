from crewai import Task
from src.agents import (
    trend_analyst,
    cmdb_correlator,
    root_cause_investigator,
    known_error_author,
    change_proposer,
)

# ══════════════════════════════════════════════════════════════════════════════
# Task 1 — Pattern Detection
# ══════════════════════════════════════════════════════════════════════════════
task_detect_patterns = Task(
    description=(
        "Analyze the FinServe Q1 2026 incident data to identify recurring problem patterns.\n\n"
        "Steps to follow:\n"
        "1. Use find_patterns to group all incidents by service + subcategory + error_code "
        "   with a minimum cluster size of 3.\n"
        "2. For each significant cluster (5+ incidents), use get_time_distribution to check "
        "   whether the pattern is temporal (day-of-week or hour clustering).\n"
        "3. Use calculate_impact to compute total downtime for each top cluster.\n"
        "4. Use parse_incidents to read the resolution_notes for top clusters — "
        "   service desk responders often leave root cause clues there.\n\n"
        "Look for at least 2–4 distinct patterns. A pattern is distinct if it involves a "
        "different service, different error code, or different temporal signature.\n\n"
        "Report each pattern with: cluster key (service/subcategory/error_code), incident count, "
        "priority breakdown, total downtime hours, temporal signature (if any), "
        "and sample incident IDs."
    ),
    expected_output=(
        "A JSON array of candidate problem patterns. Each entry must include:\n"
        "- pattern_id: e.g. PAT-001\n"
        "- service: affected service name\n"
        "- subcategory: incident subcategory\n"
        "- error_code: grouping error code\n"
        "- incident_count: integer\n"
        "- incident_ids: list of IDs in this cluster\n"
        "- priority_breakdown: dict of priority → count\n"
        "- total_downtime_hours: float\n"
        "- temporal_signature: description of any day/time clustering, or 'none'\n"
        "- sample_resolution_notes: list of 2–3 resolution notes from incidents in this cluster"
    ),
    agent=trend_analyst,
)

# ══════════════════════════════════════════════════════════════════════════════
# Task 2 — CMDB & Change Correlation
# ══════════════════════════════════════════════════════════════════════════════
task_correlate_cmdb = Task(
    description=(
        "Take the candidate patterns from the Trend Analyst and enrich each one with "
        "CMDB metadata, change log records, and infrastructure dependency data.\n\n"
        "For each pattern:\n"
        "1. Use query_cmdb to retrieve the full CMDB record for the affected CI.\n"
        "2. Use map_dependencies to identify upstream and downstream CIs — the root cause "
        "   may be in a dependency, not the incident CI itself.\n"
        "3. Use correlate_incidents_changes with a 7-day window to find changes that "
        "   occurred before incidents in this cluster.\n"
        "4. Use build_timeline to construct a merged chronological view of incidents + changes "
        "   for this pattern — look for changes that immediately precede incident spikes.\n\n"
        "Identify the single most likely related change for each pattern (if any)."
    ),
    expected_output=(
        "A JSON array of enriched patterns. Each entry extends the Trend Analyst's output with:\n"
        "- ci_details: full CMDB record for the CI\n"
        "- upstream_dependencies: list of upstream CI IDs\n"
        "- downstream_dependents: list of downstream CI IDs\n"
        "- correlated_changes: list of changes found in the pre-incident window\n"
        "- most_likely_change: the single change ID most likely linked to this pattern, "
        "  with a one-sentence justification (or 'none' if no change correlates)\n"
        "- timeline_summary: top 5 chronological events (incident or change) for this pattern"
    ),
    agent=cmdb_correlator,
    context=[task_detect_patterns],
)

# ══════════════════════════════════════════════════════════════════════════════
# Task 3 — Root Cause Analysis
# ══════════════════════════════════════════════════════════════════════════════
task_root_cause = Task(
    description=(
        "For each enriched pattern, determine the specific root cause using the Five Whys technique.\n\n"
        "For each pattern:\n"
        "1. Use five_whys_analysis — pass the pattern summary, CMDB data, and change data as inputs. "
        "   Work through each 'why' step methodically, citing evidence at each step.\n"
        "2. Use build_timeline to confirm the sequence of events supports your causal chain.\n"
        "3. Use parse_incidents to check resolution_notes for additional clues.\n"
        "4. Once the root cause is confirmed, use create_problem_record to save a formal "
        "   Problem Record (PROB-001, PROB-002, etc.) to the output directory.\n\n"
        "A root cause must be specific. 'Memory leak' is not specific enough. "
        "'Batch reconciliation job CHG0042 deployed without heap limits, causing OOM on weekly runs' is specific.\n\n"
        "Each root cause must be supported by at least 2 pieces of evidence."
    ),
    expected_output=(
        "A JSON array of root cause determinations. Each entry must include:\n"
        "- problem_id: e.g. PROB-001 (matching the saved Problem Record)\n"
        "- pattern_id: links back to Trend Analyst output\n"
        "- five_whys_chain: list of 5 dicts, each with 'why' and 'answer_with_evidence'\n"
        "- root_cause_statement: one clear sentence stating the root cause\n"
        "- supporting_evidence: list of at least 2 evidence items (incident IDs, change IDs, CMDB facts)\n"
        "- problem_record_saved: true/false"
    ),
    agent=root_cause_investigator,
    context=[task_detect_patterns, task_correlate_cmdb],
)

# ══════════════════════════════════════════════════════════════════════════════
# Task 4 — Known Error Documentation
# ══════════════════════════════════════════════════════════════════════════════
task_known_errors = Task(
    description=(
        "For each confirmed root cause, create a complete Known Error Record and save it to "
        "the output directory using the create_known_error tool.\n\n"
        "Each Known Error Record must include:\n"
        "- A clear root_cause statement (taken from the Root Cause Investigator's output)\n"
        "- A workaround: step-by-step instructions the Service Desk can follow RIGHT NOW to "
        "  resolve a new incident of this type quickly. Be specific — 'restart the service' "
        "  is not acceptable. Say exactly which service, which command, what to check first.\n"
        "- A permanent_fix: description of what engineering must change to eliminate this problem.\n\n"
        "Also use calculate_impact for each pattern to include business impact metrics in your summary."
    ),
    expected_output=(
        "A JSON array of Known Error Records. Each entry must include:\n"
        "- ke_id: e.g. KE-001\n"
        "- problem_id: links to Problem Record\n"
        "- root_cause: confirmed root cause statement\n"
        "- workaround: numbered step-by-step instructions (at least 3 steps)\n"
        "- permanent_fix: description of the engineering change required\n"
        "- affected_ci: primary CI\n"
        "- linked_incidents: list of incident IDs\n"
        "- business_impact: dict with total_incidents, total_downtime_hours, priority_breakdown\n"
        "- file_saved: path to the saved JSON file"
    ),
    agent=known_error_author,
    context=[task_root_cause],
)

# ══════════════════════════════════════════════════════════════════════════════
# Task 5 — Change Proposals & Final Report
# ══════════════════════════════════════════════════════════════════════════════
task_change_proposals = Task(
    description=(
        "For each Known Error Record, produce a formal Request for Change (RFC) and save it "
        "using the create_rfc tool. Then write the final Problem Management Summary Report.\n\n"
        "For each RFC:\n"
        "- Select the appropriate change_type: Emergency (service still degraded), "
        "  Normal (standard CAB review needed), or Standard (pre-approved low-risk).\n"
        "- Assign a risk_rating: High (touches production core systems), "
        "  Medium (touches supporting services), Low (config-only changes).\n"
        "- Write a specific test_plan — at minimum: unit test scope, integration test scope, "
        "  load/performance test requirement, and rollback trigger criteria.\n"
        "- Write a rollback_plan — step-by-step instructions to revert the change.\n"
        "- Propose a realistic implementation_date (use 2026-04-xx or 2026-05-xx dates).\n\n"
        "After saving all RFCs, write the Final Problem Management Summary Report as a "
        "formatted Markdown string. The report should have sections: Executive Summary, "
        "Patterns Detected, Root Causes, Known Errors, and Change Proposals."
    ),
    expected_output=(
        "1. A JSON array of RFC records, each with:\n"
        "   - rfc_id, ke_id, title, description, change_type, risk_rating,\n"
        "     test_plan, rollback_plan, planned_implementation, file_saved\n\n"
        "2. A complete Markdown Problem Management Report with these sections:\n"
        "   ## Executive Summary\n"
        "   ## Patterns Detected (table: pattern_id, service, count, downtime)\n"
        "   ## Root Cause Analysis (one subsection per problem)\n"
        "   ## Known Error Records (ke_id, root_cause, workaround summary)\n"
        "   ## Change Proposals (rfc_id, title, change_type, risk, planned date)\n"
        "   ## Recommendations\n"
    ),
    agent=change_proposer,
    context=[task_root_cause, task_known_errors],
)
