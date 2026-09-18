"""Test P0-2: Orphaned asyncio tasks tracking.

Verifies that asyncio.create_task() results are tracked in
_background_tasks set and cleaned up via done callbacks.
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))


class TestBackgroundTasks(unittest.TestCase):
    """Test P0-2 background task tracking."""

    def test_discard_task_callback(self):
        """_discard_task should remove completed tasks from set."""
        from api.network import _background_tasks, _discard_task

        async def dummy_task():
            return 42

        async def run_test():
            task = asyncio.create_task(dummy_task())
            task.add_done_callback(_discard_task)
            _background_tasks.add(task)

            self.assertIn(task, _background_tasks)
            result = await task
            self.assertEqual(result, 42)
            # Callback should have removed it
            self.assertNotIn(task, _background_tasks)

        asyncio.run(run_test())

    def test_multiple_tasks_cleanup(self):
        """Multiple tasks should all be cleaned up."""
        from api.network import _background_tasks, _discard_task

        async def dummy_task(n):
            await asyncio.sleep(0.01 * n)
            return n

        async def run_test():
            tasks = []
            for i in range(5):
                task = asyncio.create_task(dummy_task(i + 1))
                task.add_done_callback(_discard_task)
                _background_tasks.add(task)
                tasks.append(task)

            self.assertEqual(len(_background_tasks), 5)
            await asyncio.gather(*tasks)
            # All should be cleaned up
            self.assertEqual(len(_background_tasks), 0)

        asyncio.run(run_test())

    def test_task_with_exception(self):
        """Task with exception should still be cleaned up."""
        from api.network import _background_tasks, _discard_task

        async def failing_task():
            raise ValueError("test error")

        async def run_test():
            task = asyncio.create_task(failing_task())
            task.add_done_callback(_discard_task)
            _background_tasks.add(task)

            with self.assertRaises(ValueError):
                await task
            # Should still be removed
            self.assertNotIn(task, _background_tasks)

        asyncio.run(run_test())

    def test_background_tasks_set_is_shared(self):
        """_background_tasks should be a module-level set."""
        from api.network import _background_tasks

        self.assertIsInstance(_background_tasks, set)


if __name__ == "__main__":
    unittest.main()
