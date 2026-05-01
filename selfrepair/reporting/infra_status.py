from selfrepair.models import InfraStatus

def default_infra_status() -> list[InfraStatus]:
    return [
        InfraStatus(name="GitHub API", status="unknown", details="Checked indirectly through discovery."),
        InfraStatus(name="GitLab API", status="unknown", details="Checked indirectly through discovery."),
        InfraStatus(name="OllaBridge", status="unknown", details="LLM repair assistant availability."),
        InfraStatus(name="GitPilot", status="unknown", details="Adapter availability is checked during runs."),
        InfraStatus(name="MatrixLab", status="unknown", details="Sandbox execution availability."),
    ]
