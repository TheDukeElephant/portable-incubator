import asyncio
import time
from abc import ABC, abstractmethod

class BaseLoop(ABC):
    """
    Abstract base class for asynchronous control loops.
    Provides common structure for running, stopping, and periodic execution.
    """
    def __init__(self, manager: 'ControlManager', control_interval: float, enabled_attr: str):
        """
        Initializes the base loop.

        Args:
            manager: The ControlManager instance.
            control_interval: The time in seconds between control steps.
            enabled_attr: (Required) The attribute name in the manager that indicates
                          if this specific loop is enabled (e.g., 'temperature_enabled').
        """
        if control_interval <= 0:
            raise ValueError("Control interval must be positive.")
        if not enabled_attr or not isinstance(enabled_attr, str):
            raise ValueError("enabled_attr must be a non-empty string.")
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
        # Ensure the attribute exists on the manager before trying to access it
        if not hasattr(self.manager, self._enabled_attr):
             # Log a warning or raise an error if the attribute doesn't exist
             # For robustness, let's default to False (disabled) if attribute is missing
             print(f"Warning: Enabled attribute '{self._enabled_attr}' not found on ControlManager. Assuming disabled.")
             return False
        loop_enabled = getattr(self.manager, self._enabled_attr)
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
        print(f"[{self.__class__.__name__}] active={self._active()} main={self.manager.incubator_running} enabled={getattr(self.manager, self._enabled_attr, None)}")
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
        print(f"[{self.__class__.__name__}] run started. Checking active state...")
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
                # Only run control_step if active at the start of the iteration
                if self._active():
                    await self.control_step()
                # else: # If inactive at start, _ensure_actuator_off was already called

                # --- ADDED CHECK ---
                # Re-check active state *after* control_step potentially ran or was skipped.
                # If it became inactive during the step/check, ensure actuator is off now.
                if not self._active():
                    self._ensure_actuator_off()
                # --- END ADDED CHECK ---

            except asyncio.CancelledError:
                print(f"{self.__class__.__name__} run cancelled.")
                break # Exit loop if cancelled
            except Exception as e:
                print(f"Error in {self.__class__.__name__} control_step: {e}")
                # Decide if the loop should continue or stop on error
                # For now, continue but log the error

            # Calculate time elapsed and sleep for the remaining interval
            # Ensure elapsed_time calculation still makes sense if control_step was skipped
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