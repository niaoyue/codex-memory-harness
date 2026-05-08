from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InstallDryRunWrapperTests(unittest.TestCase):
    def test_install_scripts_expose_dry_run_flag(self) -> None:
        powershell = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")
        batch = (PROJECT_ROOT / "install.bat").read_text(encoding="utf-8")
        shell = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("[switch]$DryRun", powershell)
        self.assertIn("--dry-run", powershell)
        self.assertIn("-DryRun", batch)
        self.assertIn("--dry-run", batch)
        self.assertIn("-DryRun", shell)
        self.assertIn("--dry-run", shell)

    def test_install_scripts_disable_auto_install_for_dry_run(self) -> None:
        batch = (PROJECT_ROOT / "install.bat").read_text(encoding="utf-8")
        shell = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn('set "DRY_RUN=0"', batch)
        self.assertIn('set "AUTO_INSTALL=0"', batch)
        self.assertIn('if "%DRY_RUN%"=="1"', batch)
        self.assertIn("DRY_RUN=0", shell)
        self.assertIn("AUTO_INSTALL=0", shell)
        self.assertIn('[ "$DRY_RUN" != "1" ] && [ "$AUTO_INSTALL" = "1" ]', shell)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
