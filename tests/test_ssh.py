"""Isolated SSH tests. Use the Python environment supplied with Ansible.

Real Ansible modules write scratch files. Real sshd parses the configuration.
A marker command replaces the service reload. No host SSH files are changed.
"""

import copy
import grp
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class SshTasksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="debian-ssh-", dir=os.environ["TMPDIR"])
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.dest = self.work / "10-ansible.conf"
        self.marker = self.work / "reload-marker"
        self.config = self.work / "sshd_config"
        self.key = self.work / "host_key"
        self.sshd = shutil.which("sshd")
        if not self.sshd:
            self.skipTest("sshd is required")
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)], check=True)
        self.config.write_text(f"Include {self.work}/*.conf\n")
        self.tasks = [copy.deepcopy(task) for task in yaml.safe_load(
            (ROOT / "tasks/network.yml").read_text()) if "ssh" in task.get("tags", [])]
        for task in self.tasks:
            if "ansible.builtin.template" in task:
                task["ansible.builtin.template"].update(
                    src=str(ROOT / "templates/sshd.conf.j2"), dest=str(self.dest),
                    owner=pwd.getpwuid(os.getuid()).pw_name,
                    group=grp.getgrgid(os.getgid()).gr_name)
            if "ansible.builtin.file" in task:
                task["ansible.builtin.file"]["path"] = str(self.dest)
        self.handlers = [copy.deepcopy(handler) for handler in yaml.safe_load(
            (ROOT / "handlers/main.yml").read_text()) if handler["name"] in (
                "Validate SSH configuration", "Reload SSH")]
        self.assertEqual([handler["name"] for handler in self.handlers],
                         ["Validate SSH configuration", "Reload SSH"])
        for handler in self.handlers:
            self.assertNotIn("listen", handler)
            if handler["name"] == "Validate SSH configuration":
                handler["ansible.builtin.command"] = {"argv": self.sshd_command("-t")}
            else:
                handler.pop("ansible.builtin.systemd")
                handler["ansible.builtin.command"] = {"argv": ["touch", str(self.marker)]}
                handler["changed_when"] = True

    def sshd_command(self, mode):
        return [self.sshd, mode, "-h", str(self.key), "-f", str(self.config)]

    def apply(self, manage=True, password=False, success=True):
        self.marker.unlink(missing_ok=True)
        play = [{"name": "Isolated SSH tasks", "hosts": "localhost", "gather_facts": False,
                 "vars": {"ansible_python_interpreter": sys.executable,
                          "ansible_remote_tmp": str(self.work / "remote-tmp"),
                          "debian_ssh_manage": manage, "debian_ssh_password_auth": password},
                 "tasks": self.tasks, "handlers": self.handlers}]
        path = self.work / "play.yml"
        path.write_text(yaml.safe_dump(play, sort_keys=False))
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local", str(path)],
                                env=dict(os.environ, ANSIBLE_NOCOLOR="1",
                                         ANSIBLE_LOCAL_TEMP=str(self.work / "local-tmp")),
                                capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def effective(self, connection=None):
        command = self.sshd_command("-T")
        if connection:
            command.extend(["-C", connection])
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return dict(line.split(" ", 1) for line in result.stdout.splitlines())

    def test_policy_lifecycle_and_precedence(self):
        (self.work / "50-existing.conf").write_text(
            "PasswordAuthentication yes\nKbdInteractiveAuthentication yes\n")
        self.assertEqual(self.effective()["passwordauthentication"], "yes")
        self.apply()
        self.assertTrue(self.marker.exists())
        self.assertEqual(self.dest.read_text(),
                         "PasswordAuthentication no\nKbdInteractiveAuthentication no\n")
        self.assertEqual(self.effective()["passwordauthentication"], "no")
        self.assertEqual(self.effective()["kbdinteractiveauthentication"], "no")
        self.apply()
        self.assertFalse(self.marker.exists())
        self.apply(password=True)
        self.assertTrue(self.marker.exists())
        self.assertEqual(self.effective()["passwordauthentication"], "yes")
        self.assertEqual(self.effective()["kbdinteractiveauthentication"], "yes")
        self.apply(manage=False)
        self.assertFalse(self.dest.exists())
        self.assertTrue(self.marker.exists())
        self.assertEqual(self.effective()["passwordauthentication"], "yes")
        self.apply(manage=False, password=True)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.dest.exists())

    def test_match_exception_is_preserved(self):
        self.apply()
        with self.config.open("a") as config:
            config.write("Match User recovery\n  PasswordAuthentication yes\n"
                         "  KbdInteractiveAuthentication yes\n")
        effective = self.effective("user=recovery,host=localhost,addr=192.0.2.1")
        self.assertEqual(effective["passwordauthentication"], "yes")
        self.assertEqual(effective["kbdinteractiveauthentication"], "yes")
        self.assertEqual(self.effective("user=ordinary,host=localhost,addr=192.0.2.1")
                         ["passwordauthentication"], "no")

    def test_invalid_configuration_blocks_reload(self):
        (self.work / "50-invalid.conf").write_text("NotAnSshDirective yes\n")
        result = self.apply(success=False)
        self.assertIn("Bad configuration option", result.stdout + result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertTrue(self.dest.exists())
        result = self.apply(manage=False, success=False)
        self.assertIn("Bad configuration option", result.stdout + result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
