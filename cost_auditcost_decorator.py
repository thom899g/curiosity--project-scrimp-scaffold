"""
Hard Cost Ceiling Decorator System
Enforces maximum spend per function/mission with automatic termination.
"""
import functools
import time
import logging
from typing import Callable, Any, Dict, Optional
from dataclasses import dataclass, field
from decimal import Decimal
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

@dataclass
class CostMetrics:
    """Track cost metrics for a function execution"""
    tokens_in: int = 0
    tokens_out: int = 0
    api_calls: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    total_cost: Decimal = Decimal('0.00')
    
    @property
    def duration(self) -> float:
        return (self.end_time or time.time()) - self.start_time
    
    def add_api_call(self, tokens_in: int, tokens_out: int, cost: Decimal) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.api_calls += 1
        self.total_cost += cost

class CostLimitExceeded(Exception):
    """Raised when cost limit is exceeded"""
    def __init__(self, limit: Decimal, actual: Decimal, function_name: str):
        self.limit = limit
        self.actual = actual
        self.function_name = function_name
        super().__init__(
            f"Cost limit {limit} exceeded in {function_name}: {actual} spent"
        )

class CostTracker:
    """Thread-safe cost tracker"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._metrics: Dict[str, CostMetrics] = {}
        self._global_metrics = CostMetrics()
        
    def start_tracking(self, function_name: str) -> None:
        """Start tracking costs for a function"""
        with self._lock:
            self._metrics[function_name] = CostMetrics()
    
    def record_api_call(self, function_name: str, tokens_in: int