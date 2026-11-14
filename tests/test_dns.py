"""Isolated DNS task tests: run with the Python environment used by Ansible.

The template module performs real writes in scratch space. A local action plugin
simulates service state; no controller services or /etc files are modified.
"""

import copy
import json
import os
from pathlib import Path
import pwd
import grp
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PLUGIN = '''from pathlib import Path
import json
from ansible.plugins.action import ActionBase

class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        result = super().run(tmp, task_vars)
        dest = Path(task_vars["dns_test_dest"])
        if dest.is_symlink() or not dest.is_file():
            return dict(result, failed=True, msg="DNS file must be regular before stopping resolver")
        state_path = Path(task_vars["dns_test_service"])
        previous = json.loads(state_path.read_text())
        desired = self._task.args
        changed = previous != desired
        state_path.write_text(json.dumps(desired))
        return dict(result, changed=changed)
'''


class DnsTasksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="debian-dns-", dir=os.environ["TMPDIR"])
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.dest = self.work / "resolv.conf"
        self.target = self.work / "runtime-resolv.conf"
        self.service = self.work / "service.json"
        self.initial_service = {"name": "systemd-resolved.service", "state": "started", "enabled": True}
        self.service.write_text(json.dumps(self.initial_service))
        plugins = self.work / "action_plugins"
        plugins.mkdir()
        (plugins / "dns_test_service.py").write_text(SERVICE_PLUGIN)
        self.env = dict(os.environ, ANSIBLE_ACTION_PLUGINS=str(plugins), ANSIBLE_NOCOLOR="1",
                        ANSIBLE_LOCAL_TEMP=str(self.work / "local-tmp"))
        self.tasks = [copy.deepcopy(task) for task in yaml.safe_load(
            (ROOT / "tasks/network.yml").read_text()) if "dns" in task.get("tags", [])]
        for task in self.tasks:
            if "ansible.builtin.template" in task:
                args = task["ansible.builtin.template"]
                args.update(src=str(ROOT / "templates" / args["src"]), dest=str(self.dest),
                            owner=pwd.getpwuid(os.getuid()).pw_name,
                            group=grp.getgrgid(os.getgid()).gr_name)
            if "ansible.builtin.systemd" in task:
                task["dns_test_service"] = task.pop("ansible.builtin.systemd")

    def run_tasks(self, servers=None, installed=True, fail_write=False, fail_render=False):
        tasks = copy.deepcopy(self.tasks)
        if fail_write:
            for task in tasks:
                if "ansible.builtin.template" in task:
                    task["ansible.builtin.template"]["validate"] = "/bin/false %s"
        if fail_render:
            for task in tasks:
                if "ansible.builtin.template" in task:
                    task["ansible.builtin.template"]["src"] = str(self.work / "missing-template.j2")
        play = [{"name": "Isolated DNS tasks", "hosts": "localhost", "gather_facts": False,
                 "vars": {"ansible_python_interpreter": sys.executable,
                          "ansible_remote_tmp": str(self.work / "remote-tmp"),
                          "ansible_managed": "Ansible managed",
                          "ansible_facts": {"packages": {"systemd-resolved": []} if installed else {}},
                          "debian_dns_servers": ["192.0.2.53", "192.0.2.54"] if servers is None else servers,
                          "debian_search_domain": "",
                          "dns_test_dest": str(self.dest), "dns_test_service": str(self.service)},
                 "tasks": tasks}]
        playbook = self.work / "play.yml"
        playbook.write_text(yaml.safe_dump(play, sort_keys=False))
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
                                env=self.env, text=True, capture_output=True)
        if not (fail_write or fail_render):
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_file_variants_and_idempotence(self):
        expected = "#\n# Ansible managed\n#\n\nnameserver 192.0.2.53\nnameserver 192.0.2.54\n"
        for initial in ("absent", "regular", "symlink", "identical_symlink", "dangling_symlink"):
            with self.subTest(initial=initial):
                if self.dest.exists() or self.dest.is_symlink():
                    self.dest.unlink()
                if self.target.exists():
                    self.target.unlink()
                self.service.write_text(json.dumps(self.initial_service))
                original = expected if initial == "identical_symlink" else "nameserver 127.0.0.53\n"
                if initial == "regular":
                    self.dest.write_text(original)
                elif "symlink" in initial:
                    if initial != "dangling_symlink":
                        self.target.write_text(original)
                    self.dest.symlink_to(self.target)
                self.run_tasks()
                self.assertFalse(self.dest.is_symlink())
                self.assertEqual(self.dest.read_text(), expected)
                self.assertEqual(self.dest.stat().st_mode & 0o777, 0o644)
                if "symlink" in initial:
                    if initial == "dangling_symlink":
                        self.assertFalse(self.target.exists())
                    else:
                        self.assertEqual(self.target.read_text(), original)
                self.assertEqual(json.loads(self.service.read_text()),
                                 {"name": "systemd-resolved.service", "state": "stopped", "enabled": False})
                repeat = self.run_tasks()
                self.assertRegex(repeat.stdout, r"changed=0\s")

    def test_empty_list_leaves_file_and_service_untouched(self):
        self.target.write_text("original\n")
        self.dest.symlink_to(self.target)
        before = self.service.read_text()
        result = self.run_tasks(servers=[])
        self.assertTrue(self.dest.is_symlink())
        self.assertEqual(self.target.read_text(), "original\n")
        self.assertEqual(self.service.read_text(), before)
        self.assertRegex(result.stdout, r"changed=0\s")

    def test_absent_resolver_package_only_writes_file(self):
        before = self.service.read_text()
        self.run_tasks(installed=False)
        self.assertTrue(self.dest.is_file())
        self.assertEqual(self.service.read_text(), before)

    def test_failed_write_does_not_stop_resolver(self):
        self.dest.write_text("nameserver 127.0.0.53\n")
        before = self.service.read_text()
        result = self.run_tasks(fail_write=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed to validate", result.stdout)
        self.assertEqual(self.service.read_text(), before)
        self.assertEqual(self.dest.read_text(), "nameserver 127.0.0.53\n")

    def test_failed_render_preserves_symlink_and_resolver(self):
        self.target.write_text("nameserver 127.0.0.53\n")
        self.dest.symlink_to(self.target)
        before = self.service.read_text()
        result = self.run_tasks(fail_render=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing-template.j2", result.stdout)
        self.assertEqual(self.service.read_text(), before)
        self.assertTrue(self.dest.is_symlink())
        self.assertEqual(self.target.read_text(), "nameserver 127.0.0.53\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
