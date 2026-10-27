"""Estimate a remaining full comparison within an unchanged recovery deadline."""

import math


def measured_followup_budget(started_at, finished_at, now, deadline):
    values = (started_at, finished_at, now, deadline)
    assert all(type(value) in (int, float) and math.isfinite(value) for value in values)
    assert started_at < finished_at <= now < deadline
    duration = finished_at - started_at
    # The first complete stage includes VM preparation and evidence transfer.
    # Reserve another 10% plus five minutes for the second engine's startup.
    # This estimate never extends the independent NAS recovery deadline.
    minimum_stage_seconds = math.ceil(duration * 1.1) + 300
    restore_margin_seconds = 900
    remaining_seconds = deadline - now
    return {
        'observed_first_full_stage_seconds': duration,
        'minimum_stage_seconds': minimum_stage_seconds,
        'restore_margin_seconds': restore_margin_seconds,
        'deadline_epoch': deadline,
        'remaining_seconds': remaining_seconds,
        'admitted': remaining_seconds >= minimum_stage_seconds + restore_margin_seconds,
        'full_release_success_proven': False,
        'watchdog_deadline_extended': False,
    }
