"""Offline checks for the local launcher; never starts business services."""
import importlib.util
import tempfile
import unittest
from pathlib import Path


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name('dev_launcher.py')
        if path.exists():
            spec = importlib.util.spec_from_file_location('dev_launcher', path)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)
        else:
            cls.module = None

    def launcher(self):
        self.assertIsNotNone(self.module, 'The double-click launcher is not implemented yet')
        return self.module

    def test_remote_database_is_never_migrated_automatically(self):
        mod = self.launcher()
        self.assertFalse(mod.local_database('postgresql+psycopg://u:p@db.example.com/serviceos_dev'))
        self.assertFalse(mod.local_database('postgresql+psycopg://u:p@127.0.0.1/production'))
        self.assertTrue(mod.local_database('postgresql+psycopg://u:p@127.0.0.1:55432/serviceos_dev'))

    def test_missing_provider_does_not_enable_agent(self):
        mod = self.launcher()
        self.assertFalse(mod.agent_enabled({'SERVICEOS_LLM_MODEL': 'model'}))
        configured = dict(SERVICEOS_LLM_MODEL='model', SERVICEOS_LLM_BASE_URL='https://example.com', SERVICEOS_LLM_API_KEY='test')
        self.assertFalse(mod.agent_enabled(configured))
        self.assertTrue(mod.agent_enabled({**configured, 'SERVICEOS_START_AGENT': '1'}))

    def test_agent_worker_count_is_explicit_and_bounded(self):
        mod = self.launcher()
        for value, expected in [(None, 1), ('3', 3), ('0', 1), ('999', 4), ('invalid', 1)]:
            env = {} if value is None else {'SERVICEOS_AGENT_WORKERS': value}
            self.assertEqual(mod.agent_worker_count(env), expected)

    def test_existing_environment_file_is_preserved(self):
        mod = self.launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'backend').mkdir()
            (root / 'backend/.env.example').write_text('SAMPLE=1\n', encoding='utf-8')
            existing = root / 'backend/.env'
            existing.write_text('KEEP=this\n', encoding='utf-8')
            mod.ensure_environment(root)
            self.assertEqual(existing.read_text(encoding='utf-8'), 'KEEP=this\n')

    def test_first_run_creates_only_example_environment(self):
        mod = self.launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'backend').mkdir()
            (root / 'backend/.env.example').write_text('LOCAL=1\n', encoding='utf-8')
            mod.ensure_environment(root)
            self.assertEqual((root / 'backend/.env').read_text(encoding='utf-8'), 'LOCAL=1\n')


if __name__ == '__main__':
    unittest.main()
