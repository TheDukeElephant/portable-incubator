import asyncio
import time
from abc import ABC, abstractmethod

class BaseLoop(ABC):
    """
    Abstract base class for asynchronous control loops.
    Provides common structure for running, stopping, and periodic execution.
    """
    def __init__(self, manager: 'ControlManager', control_interval: float, enabled_attr: str = None):
        """
        Initializes the base loop.

        Args:
            manager: The ControlManager instance.
            control_interval: The time in seconds between control steps.
            enabled_attr: The attribute name in the manager that indicates if this loop is enabled.
        """
        if control_interval <= 0:
            raise ValueError("Control interval must be positive.")
        from .manager import ControlManager
        if not isinstance(manager, ControlManager):
            raise TypeError("Manager must be an instance of ControlManager")
        self.manager = manager
        self.control_interval = control_interval
        self._enabled_attr = enabled_attr
        self._is_running = False
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    def _active(self) -> bool:
        """
        Returns True only when the main incubator is running AND this specific
        loop is enabled via its corresponding flag in the ControlManager.
        """
        # Check BOTH the main incubator status and the specific enabled flag
        loop_enabled = getattr(self.manager, self._enabled_attr, True) if self._enabled_attr else True
        return self.manager.incubator_running and loop_enabled

    @abstractmethod
    def _ensure_actuator_off(self):
        """
        Ensure the actuator(s) controlled by this loop are turned off.
        This is called when the loop becomes inactive (_active() returns False).
        Must be implemented by subclasses.
        """
        pass

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
            if not self._active():
                self._ensure_actuator_off()
                await asyncio.sleep(self.control_interval)
                continue
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