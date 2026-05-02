from __future__ import annotations

from selfrepair.site.generator import generate_site


def test_publish_site_empty(temp_settings):
    generate_site(temp_settings)
    assert (temp_settings.status_site_dir / "data" / "repos.json").exists()
