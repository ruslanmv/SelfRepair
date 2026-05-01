from selfrepair.models import Incident, RepoHealthReport

def incidents_from_reports(reports: list[RepoHealthReport]) -> list[Incident]:
    incidents: list[Incident] = []
    for report in reports:
        if report.status == "down":
            incidents.append(
                Incident(
                    title=f"{report.repo.full_name} is down",
                    status="down",
                    details="; ".join(report.notes) or "Verification failed",
                )
            )
    return incidents
