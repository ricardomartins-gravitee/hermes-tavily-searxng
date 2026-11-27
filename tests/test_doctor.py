"""Optional integration check against a real installed Hermes CLI."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class HermesDoctorTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('hermes'), 'Hermes CLI not installed')
    def test_plugin_doctor_loads_backend(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            env = os.environ.copy()
            env.update(HERMES_HOME=temp, TMPDIR=temp)
            result = subprocess.run(['hermes', 'plugins', 'doctor', str(ROOT / 'tavily_searxng'), '--ci'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('runtime discovery, manifest parsing, import, and registration passed', result.stdout)
