"""Tests for the environment the BATCH worker pool hands to its worker processes (web_gui)."""

import os
import unittest
from unittest import mock

from src.swtorsim import web_gui

_HELPERS = "C:/Program Files/JetBrains/PyCharm 2026.1.2/plugins/python-ce/helpers"
_REPO = r"C:\Users\Rafael\Desktop\SwtorSim"


def _pycharm_python_path():
    return os.pathsep.join(
        [
            _REPO,
            _REPO + r"\src",
            _HELPERS + "/pycharm_plotly_backend",
            _HELPERS + "/pycharm_altair_backend",
            _HELPERS + "/pycharm_matplotlib_backend",
            _HELPERS + "/pycharm_display",
        ]
    )


class PrepareWorkerEnvironmentTests(unittest.TestCase):
    def test_pycharm_plot_helper_dirs_are_removed_and_order_is_kept(self):
        with mock.patch.dict(os.environ, {"PYTHONPATH": _pycharm_python_path()}):
            web_gui._prepare_worker_environment()
            self.assertEqual(
                os.environ["PYTHONPATH"].split(os.pathsep),
                [_REPO, _REPO + r"\src", _HELPERS + "/pycharm_display"],
            )

    def test_backslash_and_trailing_separator_entries_are_recognised(self):
        entry = r"C:\Program Files\JetBrains\PyCharm\plugins\python-ce\helpers\PyCharm_Matplotlib_Backend" + "\\"
        with mock.patch.dict(os.environ, {"PYTHONPATH": os.pathsep.join([_REPO, entry])}):
            web_gui._prepare_worker_environment()
            self.assertEqual(os.environ["PYTHONPATH"], _REPO)

    def test_python_path_without_helpers_is_left_untouched(self):
        original = os.pathsep.join([_REPO, _REPO + r"\src", r"C:\libs\my_backend"])
        with mock.patch.dict(os.environ, {"PYTHONPATH": original}):
            web_gui._prepare_worker_environment()
            self.assertEqual(os.environ["PYTHONPATH"], original)

    def test_python_path_of_only_helpers_is_unset(self):
        with mock.patch.dict(os.environ, {"PYTHONPATH": _HELPERS + "/pycharm_matplotlib_backend"}):
            web_gui._prepare_worker_environment()
            self.assertNotIn("PYTHONPATH", os.environ)

    def test_missing_python_path_is_not_created(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("PYTHONPATH", None)
            web_gui._prepare_worker_environment()
            self.assertNotIn("PYTHONPATH", os.environ)

    def test_openblas_threads_default_to_one(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("OPENBLAS_NUM_THREADS", None)
            web_gui._prepare_worker_environment()
            self.assertEqual(os.environ["OPENBLAS_NUM_THREADS"], "1")

    def test_explicit_openblas_threads_value_is_respected(self):
        with mock.patch.dict(os.environ, {"OPENBLAS_NUM_THREADS": "8"}):
            web_gui._prepare_worker_environment()
            self.assertEqual(os.environ["OPENBLAS_NUM_THREADS"], "8")


class PoolCreationEnvironmentTests(unittest.TestCase):
    def test_environment_is_cleaned_before_workers_are_spawned(self):
        seen = {}

        def fake_pool(**kwargs):
            # Workers copy os.environ at spawn time, i.e. inside Pool().
            seen["python_path"] = os.environ.get("PYTHONPATH")
            seen["openblas"] = os.environ.get("OPENBLAS_NUM_THREADS")
            seen["processes"] = kwargs["processes"]
            return mock.Mock()

        with (
            mock.patch.dict(os.environ, {"PYTHONPATH": _pycharm_python_path()}),
            mock.patch.object(web_gui, "_GLOBAL_SIMULATION_POOL", None),
            mock.patch.object(web_gui, "_GLOBAL_SIMULATION_POOL_KEY", None),
            mock.patch.object(web_gui, "Pool", side_effect=fake_pool),
        ):
            os.environ.pop("OPENBLAS_NUM_THREADS", None)
            web_gui.get_or_create_simulation_pool(24, {}, ("key",))

        self.assertNotIn("_backend", seen["python_path"])
        self.assertIn(_REPO, seen["python_path"])
        self.assertEqual(seen["openblas"], "1")
        self.assertEqual(seen["processes"], 24)


if __name__ == "__main__":
    unittest.main()
