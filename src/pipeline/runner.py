import time


class TimeBudget:
    """Time-boxed incremental runs (nuuuwan's max_dt idea): scrapers check
    budget.expired between docs and simply stop; the next cron tick resumes."""

    def __init__(self, seconds: float):
        self.deadline = time.monotonic() + seconds

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self.deadline
