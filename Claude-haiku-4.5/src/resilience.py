"""
Retry and circuit breaker policies for resilient appointment booking
"""
import time
import random
from enum import Enum
from typing import Callable, Any, Optional, TypeVar
from datetime import datetime, timedelta

F = TypeVar('F', bound=Callable)


class RetryStrategy(Enum):
    """Retry backoff strategies"""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"      # Failing, reject calls
    HALF_OPEN = "HALF_OPEN"  # Testing if recovered


class RetryPolicy:
    """Configurable retry policy with backoff"""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay_ms: int = 100,
        max_delay_ms: int = 5000,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.initial_delay_ms = initial_delay_ms
        self.max_delay_ms = max_delay_ms
        self.strategy = strategy
        self.jitter = jitter

    def get_delay_ms(self, attempt: int) -> float:
        """Calculate delay for retry attempt (0-indexed)"""
        if attempt > self.max_retries:
            return 0

        if self.strategy == RetryStrategy.FIXED:
            delay = self.initial_delay_ms
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.initial_delay_ms * (attempt + 1)
        else:  # EXPONENTIAL
            delay = self.initial_delay_ms * (2 ** attempt)

        # Cap at max delay
        delay = min(delay, self.max_delay_ms)

        # Add jitter (±25%)
        if self.jitter:
            jitter_amount = delay * 0.25
            delay = delay + random.uniform(-jitter_amount, jitter_amount)

        return max(delay, 0)

    def retry(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        should_retry: Callable[[Exception], bool] = None
    ) -> Any:
        """
        Execute function with retry logic
        
        Args:
            func: Function to execute
            args: Positional arguments
            kwargs: Keyword arguments
            should_retry: Predicate to determine if error is retryable
                         (default: all exceptions are retryable)
        
        Returns:
            Function result on success
            
        Raises:
            Last exception if all retries exhausted
        """
        if kwargs is None:
            kwargs = {}

        if should_retry is None:
            should_retry = lambda e: True

        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries and should_retry(e):
                    delay = self.get_delay_ms(attempt)
                    time.sleep(delay / 1000.0)
                else:
                    raise

        raise last_exception


class CircuitBreaker:
    """Circuit breaker for external service calls"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_sec: int = 30,
        name: str = "default"
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.name = name
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.success_count = 0

    def call(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None
    ) -> Any:
        """
        Execute function through circuit breaker
        
        Args:
            func: Function to execute
            args: Positional arguments
            kwargs: Keyword arguments
            
        Returns:
            Function result on success
            
        Raises:
            RuntimeError: If circuit is open
            Last function exception: If function fails
        """
        if kwargs is None:
            kwargs = {}

        # Check if should attempt recovery
        if self.state == CircuitState.OPEN:
            if self._should_attempt_recovery():
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                raise RuntimeError(f"Circuit breaker '{self.name}' is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if self.last_failure_time is None:
            return False
        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout_sec

    def _on_success(self) -> None:
        """Handle successful call"""
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
        else:
            self.failure_count = 0

    def _on_failure(self) -> None:
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def status(self) -> dict:
        """Return circuit breaker status"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None
        }
