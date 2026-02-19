"""
Сервис для отслеживания и ограничения расходов на LLM API.
Основано на реализации Manus AI.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import json
from pathlib import Path
from ...layer0.logging import get_logger


class BudgetExceededError(Exception):
    """Исключение при превышении бюджетного лимита."""
    pass


class BudgetingService:
    """Сервис для отслеживания и ограничения расходов на LLM API."""

    def __init__(
        self,
        daily_limit: float = 10.0,
        monthly_limit: float = 200.0,
        data_dir: str = "./data/budgeting"
    ):
        """
        Инициализация сервиса бюджетирования.
        
        Args:
            daily_limit: Дневной лимит в USD
            monthly_limit: Месячный лимит в USD
            data_dir: Директория для хранения данных
        """
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._daily_spent: Dict[str, float] = {}
        self._monthly_spent: Dict[str, float] = {}
        
        self.logger = get_logger("budgeting")
        self.logger.info(
            f"BudgetingService инициализирован (daily: ${daily_limit}, "
            f"monthly: ${monthly_limit})"
        )
        
        # Загружаем сохранённые данные
        self._load_data()

    def _day_key(self, date: Optional[datetime] = None) -> str:
        """
        Возвращает ключ для дня.
        
        Args:
            date: Дата (по умолчанию текущая)
            
        Returns:
            Ключ в формате 'YYYY-MM-DD'
        """
        if date is None:
            date = datetime.utcnow()
        return date.strftime('%Y-%m-%d')

    def _month_key(self, date: Optional[datetime] = None) -> str:
        """
        Возвращает ключ для месяца.
        
        Args:
            date: Дата (по умолчанию текущая)
            
        Returns:
            Ключ в формате 'YYYY-MM'
        """
        if date is None:
            date = datetime.utcnow()
        return date.strftime('%Y-%m')

    def _get_data_file(self) -> Path:
        """Возвращает путь к файлу данных."""
        return self.data_dir / "budget_data.json"

    def _load_data(self) -> None:
        """Загружает данные о расходах из файла."""
        data_file = self._get_data_file()
        
        if not data_file.exists():
            self.logger.debug("Файл данных бюджетирования не найден, начинаем с нуля")
            return
        
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._daily_spent = data.get('daily_spent', {})
            self._monthly_spent = data.get('monthly_spent', {})
            
            # Очищаем старые данные (старше 60 дней)
            self._cleanup_old_data()
            
            self.logger.debug(f"Данные бюджетирования загружены из {data_file}")
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки данных бюджетирования: {e}")
            # Начинаем с чистого листа
            self._daily_spent = {}
            self._monthly_spent = {}

    def _save_data(self) -> None:
        """Сохраняет данные о расходах в файл."""
        try:
            data = {
                'daily_spent': self._daily_spent,
                'monthly_spent': self._monthly_spent,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            data_file = self._get_data_file()
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"Данные бюджетирования сохранены в {data_file}")
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения данных бюджетирования: {e}")

    def _cleanup_old_data(self) -> None:
        """Очищает старые данные (старше 60 дней)."""
        cutoff_date = datetime.utcnow() - timedelta(days=60)
        cutoff_day_key = self._day_key(cutoff_date)
        cutoff_month_key = self._month_key(cutoff_date)
        
        # Очищаем дневные данные
        old_daily_keys = [
            key for key in self._daily_spent.keys()
            if key < cutoff_day_key
        ]
        for key in old_daily_keys:
            del self._daily_spent[key]
        
        # Очищаем месячные данные
        old_monthly_keys = [
            key for key in self._monthly_spent.keys()
            if key < cutoff_month_key
        ]
        for key in old_monthly_keys:
            del self._monthly_spent[key]
        
        if old_daily_keys or old_monthly_keys:
            self.logger.debug(
                f"Очищены старые данные: {len(old_daily_keys)} дней, "
                f"{len(old_monthly_keys)} месяцев"
            )

    async def check_budget(self, estimated_cost: float = 0.0) -> None:
        """
        Проверяет, не превысит ли расход установленные лимиты.
        
        Args:
            estimated_cost: Ориентировочная стоимость запроса
            
        Raises:
            BudgetExceededError: При превышении лимита
        """
        day_key = self._day_key()
        month_key = self._month_key()
        
        daily_spent = self._daily_spent.get(day_key, 0.0)
        monthly_spent = self._monthly_spent.get(month_key, 0.0)

        if daily_spent + estimated_cost > self.daily_limit:
            error_msg = (
                f"Превышен дневной лимит бюджета: "
                f"${daily_spent:.4f} / ${self.daily_limit:.2f} "
                f"(осталось: ${self.daily_limit - daily_spent:.2f})"
            )
            self.logger.warning(error_msg)
            raise BudgetExceededError(error_msg)
        
        if monthly_spent + estimated_cost > self.monthly_limit:
            error_msg = (
                f"Превышен месячный лимит бюджета: "
                f"${monthly_spent:.4f} / ${self.monthly_limit:.2f} "
                f"(осталось: ${self.monthly_limit - monthly_spent:.2f})"
            )
            self.logger.warning(error_msg)
            raise BudgetExceededError(error_msg)
        
        self.logger.debug(
            f"Проверка бюджета пройдена (daily: ${daily_spent:.2f}/"
            f"${self.daily_limit:.2f}, monthly: ${monthly_spent:.2f}/"
            f"${self.monthly_limit:.2f})"
        )

    async def record_expense(self, cost: float) -> None:
        """
        Записывает фактический расход после завершения запроса.
        
        Args:
            cost: Стоимость запроса в USD
        """
        if cost <= 0:
            self.logger.debug(f"Пропускаем запись нулевой стоимости: ${cost:.6f}")
            return
        
        day_key = self._day_key()
        month_key = self._month_key()
        
        # Обновляем дневные расходы
        current_daily = self._daily_spent.get(day_key, 0.0)
        self._daily_spent[day_key] = current_daily + cost
        
        # Обновляем месячные расходы
        current_monthly = self._monthly_spent.get(month_key, 0.0)
        self._monthly_spent[month_key] = current_monthly + cost
        
        # Сохраняем данные
        self._save_data()
        
        self.logger.debug(
            f"Записан расход: ${cost:.6f} "
            f"(daily total: ${self._daily_spent[day_key]:.2f}, "
            f"monthly total: ${self._monthly_spent[month_key]:.2f})"
        )

    def get_daily_remaining(self, date: Optional[datetime] = None) -> float:
        """
        Возвращает оставшийся дневной бюджет.
        
        Args:
            date: Дата (по умолчанию текущая)
            
        Returns:
            Оставшийся бюджет в USD
        """
        day_key = self._day_key(date)
        daily_spent = self._daily_spent.get(day_key, 0.0)
        remaining = max(0.0, self.daily_limit - daily_spent)
        return remaining

    def get_monthly_remaining(self, date: Optional[datetime] = None) -> float:
        """
        Возвращает оставшийся месячный бюджет.
        
        Args:
            date: Дата (по умолчанию текущая)
            
        Returns:
            Оставшийся бюджет в USD
        """
        month_key = self._month_key(date)
        monthly_spent = self._monthly_spent.get(month_key, 0.0)
        remaining = max(0.0, self.monthly_limit - monthly_spent)
        return remaining

    def get_stats(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Возвращает статистику бюджетирования.
        
        Args:
            date: Дата (по умолчанию текущая)
            
        Returns:
            Словарь со статистикой
        """
        if date is None:
            date = datetime.utcnow()
        
        day_key = self._day_key(date)
        month_key = self._month_key(date)
        
        daily_spent = self._daily_spent.get(day_key, 0.0)
        monthly_spent = self._monthly_spent.get(month_key, 0.0)
        
        daily_remaining = self.get_daily_remaining(date)
        monthly_remaining = self.get_monthly_remaining(date)
        
        return {
            "date": date.isoformat(),
            "daily": {
                "limit": self.daily_limit,
                "spent": daily_spent,
                "remaining": daily_remaining,
                "percentage": (daily_spent / self.daily_limit * 100) if self.daily_limit > 0 else 0,
                "is_exceeded": daily_spent > self.daily_limit
            },
            "monthly": {
                "limit": self.monthly_limit,
                "spent": monthly_spent,
                "remaining": monthly_remaining,
                "percentage": (monthly_spent / self.monthly_limit * 100) if self.monthly_limit > 0 else 0,
                "is_exceeded": monthly_spent > self.monthly_limit
            },
            "total_days_tracked": len(self._daily_spent),
            "total_months_tracked": len(self._monthly_spent)
        }

    def reset(self, clear_all: bool = False) -> None:
        """
        Сбрасывает данные о расходах.
        
        Args:
            clear_all: Если True, очищает все данные, иначе только текущие периоды
        """
        if clear_all:
            self._daily_spent.clear()
            self._monthly_spent.clear()
            self.logger.info("Все данные бюджетирования очищены")
        else:
            # Очищаем только текущие периоды
            day_key = self._day_key()
            month_key = self._month_key()
            
            if day_key in self._daily_spent:
                del self._daily_spent[day_key]
            
            if month_key in self._monthly_spent:
                del self._monthly_spent[month_key]
            
            self.logger.info(f"Данные за {day_key} и {month_key} очищены")
        
        self._save_data()

    def __str__(self) -> str:
        """Строковое представление."""
        stats = self.get_stats()
        daily = stats["daily"]
        monthly = stats["monthly"]
        
        return (
            f"BudgetingService(daily: ${daily['spent']:.2f}/"
            f"${daily['limit']:.2f}, monthly: ${monthly['spent']:.2f}/"
            f"${monthly['limit']:.2f})"
        )