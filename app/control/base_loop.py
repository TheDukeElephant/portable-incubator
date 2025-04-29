import asyncio
import time
from abc import ABC, abstractmethod

class BaseLoop(ABC):
    """
    Abstract base class for asynchronous control loops.
    Provides common structure for running, stopping, and periodic execution.
    """
    def __init__(self, control_interval: float):
        """
        Initializes the base loop.

        Args:
            control_interval: The time in seconds between control steps.
        """
        if control_interval <= 0:
            raise ValueError("Control interval must be positive.")
        self.control_interval = control_interval
        self._is_running = False
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    @abstractmethod
    async def control_step(self):
        """
        Perform a single control action.
        This method must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def get_status(self) -> dict:
        """
        Return the current status of the loop.
        This method must be implemented by subclasses.
        """
        pass

    async def run(self):
        """Starts the control loop execution."""
        if self._is_running:
            print(f"{self.__class__.__name__} is already running.")
            return

        print(f"{self.__class__.__name__} control loop started.")
        self._is_running = True
        self._stop_event.clear()

        while self._is_running:
            start_time = time.monotonic()
            try:
                await self.control_step()
            except asyncio.CancelledError:
                print(f"{self.__class__.__name__} run cancelled.")
                break # Exit loop if cancelled
            except Exception as e:
                print(f"Error in {self.__class__.__name__} control_step: {e}")
                # Decide if the loop should continue or stop on error
                # For now, continue but log the error

            # Calculate time elapsed and sleep for the remaining interval
            elapsed_time = time.monotonic() - start_time
            sleep_duration = max(0, self.control_interval - elapsed_time)

            try:
                # Wait for the interval or until stop is requested
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_duration)
                # If wait_for completes without timeout, it means stop_event was set
                if self._stop_event.is_set():
                    print(f"{self.__class__.__name__} stop event received.")
                    break
            except asyncio.TimeoutError:
                # This is the normal case, timeout occurred, continue loop
                pass
            except asyncio.CancelledError:
                 print(f"{self.__class__.__name__} sleep cancelled.")
                 break # Exit loop if cancelled during sleep

        print(f"{self.__class__.__name__} control loop stopped.")
        self._is_running = False


    async def stop(self):
        """Signals the control loop to stop."""
        if self._is_running:
            print(f"Stopping {self.__class__.__name__} control loop...")
            self._is_running = False
            self._stop_event.set() # Signal the run loop to exit
            # Optional: Wait for the task to finish if needed, handled by manager usually
            # if self._task and not self._task.done():
            #     try:
            #         await asyncio.wait_for(self._task, timeout=2.0)
            #     except asyncio.TimeoutError:
            #         print(f"Warning: {self.__class__.__name__} task did not finish promptly.")
            #     except asyncio.CancelledError:
            #         pass # Expected if manager cancels tasks
        else:
             print(f"{self.__class__.__name__} loop already stopped.")