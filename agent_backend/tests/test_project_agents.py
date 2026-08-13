from pathlib import Path
from tomllib import loads
from unittest import TestCase


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ProjectAgentLayoutTests(TestCase):
    def test_expected_agent_roles_and_skill_exist(self):
        self.assertTrue((PROJECT_ROOT / "AGENTS.md").exists())
        for role in ("explorer", "pm", "builder", "tester", "reporter"):
            path = PROJECT_ROOT / ".codex" / "agents" / f"{role}.toml"
            self.assertTrue(path.exists(), role)
            self.assertEqual(loads(path.read_text(encoding="utf-8"))["name"], role)
        self.assertTrue((PROJECT_ROOT / ".codex" / "skills" / "hotspot-analysis-report" / "SKILL.md").exists())

    def test_codex_project_config_references_existing_files(self):
        config = loads((PROJECT_ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertTrue((PROJECT_ROOT / ".codex" / config["default_skill"]).exists())
        self.assertTrue((PROJECT_ROOT / ".codex" / config["instructions_file"]).exists())
