from selfrepair.inventory.github_discovery import GitHubOrgDiscovery
from selfrepair.settings import get_settings
from selfrepair.inventory.repo_inventory import save_inventory

if __name__ == "__main__":
    settings = get_settings()
    discovery = GitHubOrgDiscovery(settings)
    repos = discovery.list_repositories()
    save_inventory(settings, repos)
