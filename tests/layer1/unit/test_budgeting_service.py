"""Unit-тесты BudgetingService."""
import pytest
from vagus.layer1.budgeting import BudgetingService, BudgetExceededError


@pytest.fixture
def budgeting(tmp_path):
    return BudgetingService(
        daily_limit=1.0, monthly_limit=10.0, data_dir=str(tmp_path)
    )


@pytest.mark.asyncio
async def test_check_budget_ok(budgeting):
    await budgeting.check_budget(0.5)


@pytest.mark.asyncio
async def test_record_and_check(budgeting):
    await budgeting.record_expense(0.5)
    remaining = budgeting.get_daily_remaining()
    assert remaining <= 0.5
