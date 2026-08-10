"""Time-and-place awareness. EIRA gets told what moment it is — in spoken words,
because anything that might be echoed into a reply must already be TTS-safe."""
import os
from datetime import datetime

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty",
         7: "seventy", 8: "eighty", 9: "ninety"}


def num_words(n: int) -> str:
    """0-99 as spoken words ("forty-five")."""
    if n < 20:
        return _ONES[n]
    t, o = divmod(n, 10)
    return _TENS[t] if o == 0 else f"{_TENS[t]}-{_ONES[o]}"


def day_part(hour: int) -> str:
    if 5 <= hour < 12:
        return "in the morning"
    if 12 <= hour < 17:
        return "in the afternoon"
    if 17 <= hour < 21:
        return "in the evening"
    return "at night"


def spoken_clock(hour: int, minute: int = 0) -> str:
    """23:40 -> 'eleven forty at night'; 09:05 -> 'nine oh five in the morning'."""
    h12 = hour % 12 or 12
    hw = num_words(h12)
    part = day_part(hour)
    if minute == 0:
        return f"{hw} o'clock {part}"
    if minute < 10:
        return f"{hw} oh {num_words(minute)} {part}"
    return f"{hw} {num_words(minute)} {part}"


def is_late(now: datetime | None = None) -> bool:
    """Late enough that today's plan is really tomorrow's."""
    now = now or datetime.now()
    return now.hour >= 20 or now.hour < 6


def current_moment(now: datetime | None = None) -> str:
    now = now or datetime.now()
    loc = os.getenv("LOCATION", "Delhi")
    return (f"CURRENT MOMENT: {now.strftime('%A')}, {now.strftime('%d %B %Y')}, "
            f"{spoken_clock(now.hour, now.minute)}. Location: {loc}.")
