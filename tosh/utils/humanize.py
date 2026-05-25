"""
Human-like randomization for tosh daemon.
Avoids uniform distributions that look robotic.
"""

import random
import time
from datetime import datetime


def should_skip_cycle() -> bool:
    """
    Sometimes humans just don't do the thing.

    Returns True ~8% of the time (skip this cycle).
    """
    return random.random() < 0.08


def is_sleep_hours() -> bool:
    """Check if it's typical sleep hours (midnight-6am)."""
    hour = datetime.now().hour
    return 0 <= hour < 6


def is_weekend() -> bool:
    """Check if it's weekend."""
    return datetime.now().weekday() >= 5


def time_of_day_factor() -> float:
    """
    Adjust activity based on time of day.

    Returns multiplier:
    - Sleep hours (0-6am): 0.3 (mostly skip, occasional insomnia)
    - Early morning (6-9am): 0.7 (waking up)
    - Daytime (9am-10pm): 1.0 (normal)
    - Late night (10pm-midnight): 0.8 (winding down)
    """
    hour = datetime.now().hour

    if 0 <= hour < 6:
        # Sleep hours - rare activity (insomnia, travel)
        return 0.3 if random.random() > 0.1 else 0.8
    elif 6 <= hour < 9:
        return 0.7
    elif 22 <= hour < 24:
        return 0.8
    else:
        return 1.0


def batch_size() -> int:
    """
    Human-like batch size selection.

    Distribution:
    - Usually 35-45 (normal)
    - Sometimes 25-35 (lazy/distracted)
    - Occasionally 50-65 (productive burst)

    Adjusted by:
    - Time of day (less at night)
    - Weekend boost (~20% more)
    - Burst day boost (~50% more)
    - Daily cap slowdown (reduces as we approach limit)
    """
    base = random.gauss(40, 12)

    # Time of day adjustment
    base *= time_of_day_factor()

    # Weekend boost - more free time
    if is_weekend():
        base *= 1.2

    # Burst day - occasional productive day
    if is_burst_day():
        base *= 1.5

    # Daily cap - slow down as we approach limit
    base *= daily_cap_factor()

    return int(max(10, min(85, base)))


def delay_seconds() -> int:
    """
    Human-like delay before starting a task.

    Distribution:
    - 10% chance: got distracted (3-8 min)
    - 5% chance: eager, start immediately (0-5s)
    - 85% chance: normal (15-90s)
    """
    roll = random.random()

    if roll < 0.05:
        # Eager - start right away
        return random.randint(0, 5)
    elif roll < 0.15:
        # Distracted - took a while
        return random.randint(180, 480)
    else:
        # Normal - brief pause
        delay = random.gauss(45, 25)
        return int(max(10, min(120, delay)))


def sleep_human(reason: str = ""):
    """Sleep for a human-like duration."""
    seconds = delay_seconds()
    if reason:
        print(f"[human] {reason}: waiting {seconds}s")
    time.sleep(seconds)


def per_photo_jitter() -> float:
    """
    Random delay between photos within a batch.

    Humans don't click at machine-gun pace.
    Returns seconds to sleep between photos.

    Distribution:
    - Usually 0.1-0.5s (quick clicking)
    - Sometimes 1-3s (looking at photo)
    - Rarely 5-15s (got distracted mid-batch)
    """
    roll = random.random()

    if roll < 0.03:
        # Distracted mid-batch
        return random.uniform(5, 15)
    elif roll < 0.15:
        # Paused to look at a photo
        return random.uniform(1, 3)
    else:
        # Normal clicking pace
        return random.uniform(0.1, 0.5)


# Daily volume tracking (resets at midnight)
_daily_state_file = "/tmp/tosh_daily_volume.json"


def _load_daily_state() -> dict:
    """Load daily volume state from temp file."""
    import json
    from pathlib import Path

    try:
        state = json.loads(Path(_daily_state_file).read_text())
        # Reset if it's a new day
        if state.get("date") != datetime.now().strftime("%Y-%m-%d"):
            return {"date": datetime.now().strftime("%Y-%m-%d"), "volume": 0}
        return state
    except (FileNotFoundError, json.JSONDecodeError):
        return {"date": datetime.now().strftime("%Y-%m-%d"), "volume": 0}


def _save_daily_state(state: dict):
    """Save daily volume state."""
    import json
    from pathlib import Path

    Path(_daily_state_file).write_text(json.dumps(state))


def get_daily_volume() -> int:
    """Get photos downloaded today."""
    return _load_daily_state().get("volume", 0)


def add_daily_volume(count: int):
    """Record photos downloaded."""
    state = _load_daily_state()
    state["volume"] = state.get("volume", 0) + count
    _save_daily_state(state)


def daily_cap_factor() -> float:
    """
    Reduce activity as we approach daily soft cap.

    Soft cap: ~4000 photos/day
    - Under 2000: full speed (1.0)
    - 2000-3000: slow down (0.7)
    - 3000-4000: crawl (0.4)
    - Over 4000: mostly stop (0.1)
    """
    volume = get_daily_volume()

    if volume < 2000:
        return 1.0
    elif volume < 3000:
        return 0.7
    elif volume < 4000:
        return 0.4
    else:
        # Over cap - rare downloads only
        return 0.1 if random.random() > 0.9 else 0.0


def is_burst_day() -> bool:
    """
    ~10% of days are "burst" days where we're more active.
    Uses day-of-year for consistency within a day.
    """
    day_of_year = datetime.now().timetuple().tm_yday
    random.seed(day_of_year * 7919)  # Deterministic for the day
    result = random.random() < 0.10
    random.seed()  # Reset to true random
    return result


def is_rest_day() -> bool:
    """
    ~8% of days are "rest" days where we do minimal activity.
    Often follows burst days.
    """
    day_of_year = datetime.now().timetuple().tm_yday
    random.seed(day_of_year * 7907)
    result = random.random() < 0.08
    random.seed()
    return result


def session_active() -> bool:
    """
    Simulate user "sessions" - humans have active periods and gaps.

    Uses hour blocks with some randomness.
    Active sessions: ~3-4 hour blocks, 2-3 times per day.
    """
    hour = datetime.now().hour
    day_of_year = datetime.now().timetuple().tm_yday

    # Seed based on day so sessions are consistent within a day
    random.seed(day_of_year * 7901 + hour // 3)

    # Each 3-hour block has 60% chance of being "active"
    active = random.random() < 0.6

    random.seed()  # Reset
    return active


def should_download() -> tuple[bool, str]:
    """
    Master decision: should we download this cycle?

    Returns (should_download, reason)
    """
    # Rest day - minimal activity
    if is_rest_day():
        if random.random() < 0.85:
            return False, "rest day"

    # Check daily cap
    cap_factor = daily_cap_factor()
    if cap_factor == 0.0:
        return False, f"daily cap reached ({get_daily_volume()} today)"

    # Random skip
    if should_skip_cycle():
        return False, "random skip"

    # Session check - are we in an "active" period?
    if not session_active():
        if random.random() < 0.7:  # 70% chance to skip outside sessions
            return False, "outside active session"

    return True, "ok"


if __name__ == "__main__":
    # Test the distributions
    print("Batch size samples (20 runs):")
    sizes = [batch_size() for _ in range(20)]
    print(f"  {sizes}")
    print(f"  avg: {sum(sizes)/len(sizes):.1f}, min: {min(sizes)}, max: {max(sizes)}")

    print("\nDelay samples (20 runs):")
    delays = [delay_seconds() for _ in range(20)]
    print(f"  {delays}")
    print(f"  avg: {sum(delays)/len(delays):.1f}s, min: {min(delays)}s, max: {max(delays)}s")
