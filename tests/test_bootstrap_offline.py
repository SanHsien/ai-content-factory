from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bootstrap_offline.py"


class OfflineBootstrapTests(unittest.TestCase):
    def test_bootstrap_writes_local_path_and_launcher_without_pip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            site_packages = target / "site-packages"
            launchers = target / "bin"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo-root",
                    str(ROOT),
                    "--site-packages",
                    str(site_packages),
                    "--launcher-dir",
                    str(launchers),
                    "--python-executable",
                    sys.executable,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            result = json.loads(completed.stdout)
            self.assertEqual(result["status"], "OFFLINE_BOOTSTRAP_COMPLETE")
            self.assertEqual(result["network_required"], "no")
            self.assertEqual(result["third_party_packages_installed"], "0")
            self.assertEqual(
                (site_packages / "ai_content_factory_local.pth").read_text(
                    encoding="utf-8"
                ).strip(),
                str(ROOT / "src"),
            )
            expected_name = (
                "ai-content-factory.cmd"
                if sys.platform.startswith("win")
                else "ai-content-factory"
            )
            self.assertTrue((launchers / expected_name).is_file())

    def test_default_launcher_dir_keeps_raw_executable_parent(self) -> None:
        spec = importlib.util.spec_from_file_location("bootstrap_offline", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            executable_dir = target / ("Scripts" if sys.platform.startswith("win") else "bin")
            executable_dir.mkdir(parents=True)
            executable = executable_dir / ("python.exe" if sys.platform.startswith("win") else "python")
            original_executable = module.sys.executable
            try:
                module.sys.executable = str(executable)
                self.assertEqual(module._default_launcher_dir(), executable_dir)
            finally:
                module.sys.executable = original_executable

    @unittest.skipUnless(
        not sys.platform.startswith("win"),
        "requires a real POSIX runtime",
    )
    def test_real_posix_venv_bootstrap_stays_inside_venv(self) -> None:
        system_launchers = (
            Path("/usr/bin/ai-content-factory"),
            Path("/usr/local/bin/ai-content-factory"),
        )
        before = {path: path.exists() for path in system_launchers}
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            venv = target / ".venv"
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv)],
                check=True,
                capture_output=True,
                text=True,
            )
            venv_python = venv / "bin" / "python"
            completed = subprocess.run(
                [str(venv_python), str(SCRIPT), "--repo-root", str(ROOT)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            launcher = venv / "bin" / "ai-content-factory"
            self.assertTrue(launcher.is_file())
            self.assertEqual(Path(result["launcher"]), launcher)
            self.assertEqual(
                [path for path in system_launchers if not before[path] and path.exists()],
                [],
            )

    def test_bootstrap_rejects_a_directory_without_package_source(self) -> None:
        spec = importlib.util.spec_from_file_location("bootstrap_offline", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "package source missing"):
                module.install(
                    repo_root=target,
                    site_packages=target / "site-packages",
                    launcher_dir=target / "bin",
                    python_executable=Path(sys.executable),
                )
