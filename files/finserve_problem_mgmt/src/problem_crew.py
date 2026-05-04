from crewai import Crew, Process
from src.agents import (
    trend_analyst,
    cmdb_correlator,
    root_cause_investigator,
    known_error_author,
    change_proposer,
)
from src.tasks import (
    task_detect_patterns,
    task_correlate_cmdb,
    task_root_cause,
    task_known_errors,
    task_change_proposals,
)


def build_crew() -> Crew:
    return Crew(
        agents=[
            trend_analyst,
            cmdb_correlator,
            root_cause_investigator,
            known_error_author,
            change_proposer,
        ],
        tasks=[
            task_detect_patterns,
            task_correlate_cmdb,
            task_root_cause,
            task_known_errors,
            task_change_proposals,
        ],
        process=Process.sequential,
        verbose=True,
    )
