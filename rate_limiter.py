"""
Rate Limiter Module
===================
Lightweight in-memory rate limiting with per-email and per-IP tracking.
No external dependencies required.

Usage:
    from rate_limiter import RateLimiter
    limiter = RateLimiter()

    # Check before processing
    ok, remaining, wait = limiter.check("email", "user@example.com")
    if not ok:
        return f"Rate limited. Try again in {wait} seconds.", 429

    # Record the request
    limiter.record("email", "user@example.com")
"""

import time
import threading
from collections import defaultdict
from typing import Dict, List, Tuple


class RateLimiter:
    """
    Sliding-window in-memory rate limiter.

    Tracks requests by key (e.g., email, IP) within a time window.
    Thread-safe for concurrent Flask requests.
    """

    def __init__(self, max_requests: int = 3, window_seconds: int = 3600):
        """
        Args:
            max_requests: Maximum requests allowed within the window.
            window_seconds: Length of the sliding window in seconds (default 1 hour).
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._records: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _cleanup(self, key: str):
        """Remove timestamps outside the current window."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._records[key] = [t for t in self._records[key] if t > cutoff]

    def check(self, key: str) -> Tuple[bool, int, int]:
        """
        Check if a request is allowed for the given key.

        Returns:
            Tuple of (allowed: bool, remaining: int, retry_after_seconds: int)
        """
        with self._lock:
            self._cleanup(key)
            current_count = len(self._records[key])
            remaining = max(0, self.max_requests - current_count)

            if current_count >= self.max_requests:
                # Calculate when the oldest entry in the window expires
                oldest = min(self._records[key])
                retry_after = int(oldest + self.window_seconds - time.time())
                retry_after = max(1, retry_after)
                return False, 0, retry_after

            return True, remaining, 0

    def record(self, key: str):
        """Record a request for the given key."""
        with self._lock:
            self._records[key].append(time.time())

    def get_remaining(self, key: str) -> int:
        """Get remaining requests allowed for the given key."""
        allowed, remaining, _ = self.check(key)
        return remaining

    def reset(self, key: str):
        """Reset rate limit tracking for a key."""
        with self._lock:
            self._records.pop(key, None)


# ============================================================
# Resend Verification Limiters
# ============================================================
# Email-based: 3 resend requests per hour (per email address)
email_limiter = RateLimiter(max_requests=3, window_seconds=3600)

# IP-based: 5 resend requests per hour (per IP) — fallback if no email known
ip_limiter = RateLimiter(max_requests=5, window_seconds=3600)

# Global cooldown: 1 resend request per 120 seconds (prevents rapid clicking)
cooldown_limiter = RateLimiter(max_requests=1, window_seconds=120)

# ============================================================
# Login Brute Force Limiters
# ============================================================
# Per-IP: 10 login attempts per 15 minutes (catches broad automated attacks)
login_ip_limiter = RateLimiter(max_requests=10, window_seconds=900)

# Per-email: 5 login attempts per 15 minutes (prevents targeted account brute force)
login_email_limiter = RateLimiter(max_requests=5, window_seconds=900)

# Login cooldown: 1 attempt per 2 seconds (prevents rapid-fire automated attempts)
login_cooldown_limiter = RateLimiter(max_requests=1, window_seconds=2)

# ============================================================
# Registration Brute Force Limiters
# ============================================================
# Per-IP: 3 registrations per hour (prevents mass account creation)
register_ip_limiter = RateLimiter(max_requests=3, window_seconds=3600)
