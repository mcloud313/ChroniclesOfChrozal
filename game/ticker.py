# game/ticker.py
"""
Centralized asynchronous ticker system for game updates.
Other systems can subscribe callback functions (coroutines) that will be
awaited on each tick.
"""
import asyncio
import logging
import time
from typing import Callable, Coroutine, Any, Set, Optional

log = logging.getLogger(__name__)

# Type alias for the callback functions subscribers provide.
# They receive the delta time (dt) since the last tick as a float.
TickCallback = Callable[[float], Coroutine[Any, Any, None]]

# --- Module State ---
_callbacks: Set[TickCallback] = set()
_ticker_task: Optional[asyncio.Task] = None
_interval_seconds: float = 1.0 # Default tick interval

# --- Public API ---
def subscribe(callback: TickCallback):
    """Subscribe an async function to be called on each ticker cycle."""
    if not asyncio.iscoroutinefunction(callback):
        log.error("Ticker subscription failed: Provided callback %s is not an async function.", callback.__name__)
        return
    _callbacks.add(callback)
    log.debug("Callback %s subscribed to ticker.", callback.__name__)

def unsubscribe(callback: TickCallback):
    """Unsubscribe an async function from the ticker cycle."""
    _callbacks.discard(callback)
    log.debug("Callback %s unsubscribed from ticker.", callback.__name__)

async def start_ticker(interval_seconds: float = 1.0):
    """Starts the global ticker task if not already running."""
    global _ticker_task, _interval_seconds
    _interval_seconds = interval_seconds

    if _ticker_task and not _ticker_task.done():
        log.warning("Ticker task is already running.")
        return
    
    if interval_seconds <= 0:
        log.error("Ticker interval must be positive. Ticker not started.")
        return
    
    log.info("Starting global game ticker with interval: %.2f seconds.", interval_seconds)
    _ticker_task = asyncio.create_task(_run_ticker(), name="GameTicker")

async def stop_ticker():
    """Stops the global ticker task gracefully"""
    global _ticker_task
    if not _ticker_task or _ticker_task.done():
        log.info("Ticker task is not running or already stopped.")
        _ticker_task = None # Ensure it's cleared
        return
    
    log.info("Stopping global game ticker...")
    _ticker_task.cancel()
    try:
        # Wait for the task to acknowledge cancellation
        await asyncio.wait_for(_ticker_task, timeout=5.0)
    except asyncio.CancelledError:
        log.info("Ticker task successfully cancelled.")
    except asyncio.TimeoutError:
        log.warning("Ticker task did not finish cancelling within timeout.")
    except Exception:
        # Log any other unexpected errors during cancellation
        log.exception("Exception during ticker task cancellation:", exc_info=True)
    finally:
        _ticker_task = None # Clear task reference

# --- Internal Coroutine

async def _run_ticker():
    """The main loop that executes subscribed callbacks periodically."""
    log.debug("Ticker loop starting.")
    last_tick_time = time.monotonic()

    while True:
        try:
            log.debug("Ticker: Sleeping for %.2f s...", _interval_seconds) # ADDED
            # Wait for the next tick interval
            await asyncio.sleep(_interval_seconds)

            current_time = time.monotonic()
            delta_time = current_time - last_tick_time
            last_tick_time = current_time

            if not _callbacks: # No work to do
                continue

            log.debug("Ticker tick! Delta: %.3f s. Processing %d callbacks.", delta_time, len(_callbacks))

            # Create tasks for all subscribed callbacks for this tick
            # Copy the set in case callbacks modify it during execution
            tasks = [asyncio.create_task(cb(delta_time)) for cb in list(_callbacks)]

            if tasks:
                # Run callbacks concurrently and gather results/exceptions
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        # Log exceptions from individual callbacks but don't stop the ticker
                        callback_name = getattr(list(_callbacks)[i], '__name__', 'unknown callback')
                        log.exception("Ticker: Exception in callback '%s': %s", callback_name, result, exc_info=result)
        except asyncio.CancelledError:
            log.info("Ticker loop cancelled.")
            break # Exit the loop cleanly
        except Exception:
            # Catch unexpected errors in the ticker loop itself
            log.exception("Ticker loop encountered unexpected error:", exc_info=True)
            # Avoid tight loop on persistent error, wait before retryinig
            await asyncio.sleep(max(5.0, _interval_seconds))

    log.debug("Ticker loop finished.")