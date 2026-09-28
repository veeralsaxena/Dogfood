import time
from collections import defaultdict
from typing import Dict, Tuple

class TokenBucketRateLimiter:
    """In-memory rate limiter per IP/identity using Token Bucket algorithm."""
    def __init__(self, capacity: int = 30, refill_rate: float = 1.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens: Dict[str, float] = defaultdict(lambda: float(capacity))
        self.last_update: Dict[str, float] = defaultdict(time.time)

    def is_allowed(self, key: str, cost: float = 1.0) -> bool:
        now = time.time()
        elapsed = now - self.last_update[key]
        self.last_update[key] = now

        # Refill tokens
        self.tokens[key] = min(self.capacity, self.tokens[key] + elapsed * self.refill_rate)

        if self.tokens[key] >= cost:
            self.tokens[key] -= cost
            return True
        return False

# Global rate limiter instances
voting_limiter = TokenBucketRateLimiter(capacity=5, refill_rate=0.2) # Max 5 votes bursting, 1 per 5s
api_limiter = TokenBucketRateLimiter(capacity=60, refill_rate=2.0)   # 60 req/min
