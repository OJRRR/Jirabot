"""测试 tools/constants.py 中的状态/优先级判断函数"""
import pytest
from tools.constants import is_done, is_in_progress, is_high_priority, is_medium_priority


class TestIsDone:
    def test_done_statuses(self):
        assert is_done("Done")
        assert is_done("Closed")
        assert is_done("已完成")
        assert is_done("已关闭")

    def test_not_done(self):
        assert not is_done("To Do")
        assert not is_done("In Progress")
        assert not is_done("Open")

    def test_none_or_empty(self):
        assert not is_done(None)
        assert not is_done("")


class TestIsInProgress:
    def test_in_progress(self):
        assert is_in_progress("In Progress")
        assert is_in_progress("进行中")

    def test_not_in_progress(self):
        assert not is_in_progress("Done")
        assert not is_in_progress("To Do")


class TestIsHighPriority:
    def test_high(self):
        assert is_high_priority("Highest")
        assert is_high_priority("High")
        assert is_high_priority("高")
        assert is_high_priority("紧急")

    def test_not_high(self):
        assert not is_high_priority("Medium")
        assert not is_high_priority("Low")
        assert not is_high_priority(None)


class TestIsMediumPriority:
    def test_medium(self):
        assert is_medium_priority("Medium")
        assert is_medium_priority("中")

    def test_not_medium(self):
        assert not is_medium_priority("High")
        assert not is_medium_priority(None)
