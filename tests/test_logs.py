"""Isolated journald tests. Use the Python environment supplied with Ansible.

Real Ansible modules write scratch files. Marker commands replace restart and
flush operations. No host journal files or services are changed.
"""

import copy
import grp
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class LogsTasksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="debian-logs-", dir=os.environ["TMPDIR"])
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.directory = self.work / "journald.conf.d"
        self.dest = self.directory / "enable-persistence.conf"
        self.marker = self.work / "handler-order"
        self.tasks = copy.deepcopy(yaml.safe_load((ROOT / "tasks/logs.yml").read_text()))
        self.assertEqual(len(self.tasks), 2)
        for task in self.tasks:
            module = "ansible.builtin.file" if "ansible.builtin.file" in task else "ansible.builtin.template"
            args = task[module]
            args.update(owner=pwd.getpwuid(os.getuid()).pw_name,
                        group=grp.getgrgid(os.getgid()).gr_name)
            if module == "ansible.builtin.file":
                args["path"] = str(self.directory)
            else:
                args.update(src=str(ROOT / "templates/journald.conf.j2"), dest=str(self.dest))
                self.assertEqual(task["notify"], ["Restart journald", "Flush journald"])
        self.handlers = [copy.deepcopy(handler) for handler in yaml.safe_load(
            (ROOT / "handlers/main.yml").read_text()) if handler["name"] in (
                "Restart journald", "Flush journald")]
        self.assertEqual([handler["name"] for handler in self.handlers],
                         ["Restart journald", "Flush journald"])
        self.assertEqual(self.handlers[0]["ansible.builtin.systemd"],
                         {"name": "systemd-journald.service", "state": "restarted"})
        self.assertEqual(self.handlers[1]["ansible.builtin.command"], {"cmd": "journalctl --flush"})
        for handler in self.handlers:
            self.assertNotIn("listen", handler)
            handler.pop("ansible.builtin.systemd", None)
            handler["ansible.builtin.command"] = {"argv": [
                sys.executable, "-c",
                "from pathlib import Path; import sys; "
                "p = Path(sys.argv[1]); "
                "p.write_text((p.read_text() if p.exists() else '') + sys.argv[2] + '\\n')",
                str(self.marker), handler["name"]]}
            handler["changed_when"] = True
        includes = yaml.safe_load((ROOT / "tasks/main.yml").read_text())
        self.include = next(task for task in includes
                            if task.get("ansible.builtin.include_tasks", {}).get("file") == "logs.yml")
        self.assertEqual(self.include["when"], "debian_setup_journald | bool")

    def apply(self, enabled=True):
        self.marker.unlink(missing_ok=True)
        tasks_path = self.work / "logs.yml"
        tasks_path.write_text(yaml.safe_dump(self.tasks, sort_keys=False))
        include = copy.deepcopy(self.include)
        include["ansible.builtin.include_tasks"]["file"] = str(tasks_path)
        play = [{"name": "Isolated journald tasks", "hosts": "localhost", "gather_facts": False,
                 "vars": {"ansible_python_interpreter": sys.executable,
                          "ansible_remote_tmp": str(self.work / "remote-tmp"),
                          "ansible_managed": "Ansible managed", "debian_setup_journald": enabled},
                 "tasks": [include], "handlers": self.handlers}]
        path = self.work / "play.yml"
        path.write_text(yaml.safe_dump(play, sort_keys=False))
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local", str(path)],
                                env=dict(os.environ, ANSIBLE_NOCOLOR="1",
                                         ANSIBLE_LOCAL_TEMP=str(self.work / "local-tmp")),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_lifecycle(self):
        self.apply(enabled=False)
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.marker.exists())
        self.apply()
        self.assertIn("[Journal]\nStorage=persistent\n", self.dest.read_text())
        self.assertEqual(self.marker.read_text(), "Restart journald\nFlush journald\n")
        self.apply()
        self.assertFalse(self.marker.exists())
        self.dest.write_text("[Journal]\nStorage=volatile\n")
        self.apply()
        self.assertEqual(self.marker.read_text(), "Restart journald\nFlush journald\n")
        original = self.dest.read_bytes()
        self.apply(enabled=False)
        self.assertEqual(self.dest.read_bytes(), original)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
