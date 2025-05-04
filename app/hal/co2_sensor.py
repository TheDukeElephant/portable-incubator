from __future__ import annotations
import asyncio
import datetime as dt
import logging
from dataclasses import dataclass

import serial_asyncio

@dataclass(frozen=True)
class CO2Reading:
    ppm: int
    timestamp: dt.datetime = dt.datetime.utcnow()

class CO2Sensor:
    def __init__(self, url: str, baudrate: int = 9600,
                 init_cmd: bytes = None, read_cmd: bytes = b'Z\r\n', *,
                 timeout: float = 2.0):
        """
        Initializes the CO2 Sensor communication.

        Args:
            url (str): The serial port device path (e.g., '/dev/ttyS0', '/dev/ttyUSB0'). Required.
            baudrate (int): Serial communication baud rate.
            init_cmd (bytes): Initialization command to send to the sensor (optional).
            read_cmd (bytes): Command to send to request a reading.
            timeout (float): Read timeout in seconds.
        """
        if not url:
            raise ValueError("Serial port URL (device path) cannot be empty.")
        # Store config using 'url' key expected by serial_asyncio
        self._port_cfg = dict(url=url, baudrate=baudrate, timeout=timeout)
        self._init_cmd = init_cmd
        self._read_cmd = read_cmd
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._multiplier: int = 1 # Default multiplier

    async def __aenter__(self):  # async context manager
        logger = logging.getLogger(__name__)
        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self._port_cfg['url'],
            baudrate=self._port_cfg.get('baudrate', 9600),
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=self._port_cfg.get('timeout', 2.0)
        )
        await asyncio.sleep(0.2)
        # Original code had drain/sleep here, but open_serial_connection likely handles readiness.
        # Let's keep it simple unless issues arise.
        # await self._writer.drain()
        # await asyncio.sleep(0.1)
        if self._init_cmd:
            logging.getLogger(__name__).info(f"Sending init command: {self._init_cmd!r}")
            self._writer.write(self._init_cmd)
            await self._writer.drain()
            await asyncio.sleep(0.1)
            # Consider adding a small delay or reading response if needed

        # Query the multiplier after initialization
        try:
            logger.info("Querying sensor multiplier with '.' command.")
            self._writer.write(b'.\r\n')
            await self._writer.drain()
            await asyncio.sleep(0.1) # Give sensor time to respond
            factor_raw = await asyncio.wait_for(self._reader.readuntil(b'\n'), timeout=1.0)
            logger.debug(f"Received multiplier raw data: {factor_raw!r}")
            # Extract digits only
            digits = b''.join(ch for ch in factor_raw if ch.isdigit())
            if digits:
                self._multiplier = int(digits)
                # Handle the 0-5% or 0-20% case where multiplier is 1 but reported as 0 sometimes?
                # Manual implies '.' returns the actual multiplier (1, 10, 100).
                # Let's trust the sensor report for now. If it reports 0, we might need adjustment.
                if self._multiplier == 0:
                     logger.warning("Sensor reported multiplier 0, using 1 instead as per potential datasheet interpretation for low ranges.")
                     self._multiplier = 1 # Assume 1 if 0 is reported, common for <60% sensors
                logger.info(f"Sensor multiplier set to: {self._multiplier}")
            else:
                logger.warning(f"Could not parse multiplier from response: {factor_raw!r}. Using default multiplier 1.")
                self._multiplier = 1
        except (asyncio.TimeoutError, ValueError, Exception) as e:
            logger.warning(f"Failed to query/parse sensor multiplier: {e}. Using default multiplier 1.")
            self._multiplier = 1 # Default on error

        # Set polling mode (Mode 2) to avoid unsolicited data
        try:
            logger.info("Setting sensor to polling mode (K 2).")
            self._writer.write(b'K 2\r\n')
            await self._writer.drain()
            await asyncio.sleep(0.1) # Give sensor time to process
            # We might want to read the confirmation ' K 00002\r\n' but it's often safe to assume it worked.
            # response = await asyncio.wait_for(self._reader.readuntil(b'\n'), timeout=1.0)
            # logger.debug(f"Received response after K 2 command: {response!r}")
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Failed to set sensor polling mode: {e}")

        return self

    async def __aexit__(self, *exc):
        if self._writer and not self._writer.is_closing():
             self._writer.close()
             try:
                 await self._writer.wait_closed()
             except Exception as e:
                 logging.getLogger(__name__).warning(f"Error closing writer: {e}")
        self._reader = None
        self._writer = None


    async def read_ppm(self) -> int:
        last_err: Exception | None = None
        logger = logging.getLogger(__name__) # Get logger instance

        for attempt in range(3):
            try:
                if not self._writer or not self._reader:
                    logger.warning(f"Attempt {attempt + 1}: Sensor connection not established or closed. Attempting reinitialization.")
                    # Try to re-establish connection cleanly
                    await self.__aexit__() # Ensure closed first
                    await asyncio.sleep(0.1) # Brief pause
                    await self.__aenter__() # Re-open
                    logger.info(f"Attempt {attempt + 1}: Sensor connection reinitialized.")
                    # Continue to next part of the loop to send read command

                # Add a small delay before sending command
                await asyncio.sleep(0.1)
                logger.info(f"Attempt {attempt + 1}: Sending read command: {self._read_cmd!r}")
                self._writer.write(self._read_cmd)
                await self._writer.drain()

                # Read until carriage return
                logger.debug(f"Attempt {attempt + 1}: Waiting for response...")
                # Read until newline (\n) to consume the full response
                raw = await asyncio.wait_for(self._reader.readuntil(b'\n'), timeout=1.2)
                logger.info(f"Attempt {attempt + 1}: Received raw data: {raw!r}")
                return self._parse_ppm(raw)

            except asyncio.TimeoutError as exc:
                # Demote timeout to warning as it might be expected occasionally
                logger.warning(f"Attempt {attempt + 1}: Timeout waiting for CO2 sensor response.")
                last_err = exc
            except ValueError as exc: # Catch parsing errors specifically
                 logger.warning(f"Attempt {attempt + 1}: Error parsing CO2 sensor data: {exc}") # Also demote parsing errors? Maybe keep as error. Let's keep warning for now.
                 last_err = exc # Keep the specific parsing error
            except Exception as exc:
                logger.error(f"Attempt {attempt + 1}: Unexpected error reading CO2 sensor: {exc}", exc_info=True) # Log full traceback for unexpected errors
                last_err = exc

            # Wait before retrying
            if attempt < 2: # Only sleep if not the last attempt
                 await asyncio.sleep(0.5)

        # If loop finishes without returning, raise an error
        logger.critical(f"CO2 sensor read failed after 3 retries.")
        raise RuntimeError(f"CO2 sensor read failed after 3 retries: {last_err}") from last_err
        # --- Unreachable code below this line removed ---


    # Make _parse_ppm an instance method to access self._multiplier
    def _parse_ppm(self, raw: bytes) -> int:
        """
        Accepts:  b' Z 00473\\r\\n' or similar ASCII, or 7-byte binary frame.
        Returns:  473  (ppm)
        """
        # ––– binary frame –––
        if len(raw) == 7 and raw[0] == 0xFE:
            high, low = raw[3], raw[4]
            return (high << 8) | low                           # already ppm

        # ––– ASCII replies –––
        decoded = raw.decode('ascii', errors='ignore').strip() # 'Z 00473'
        # drop every non‑digit, keeps us safe whatever spacing SenseAir sends
        digits = ''.join(ch for ch in decoded if ch.isdigit())
        if not digits:
            # Log the problematic raw data before raising
            logging.getLogger(__name__).warning(f"Could not parse PPM: no digits found in reply: {raw!r}")
            raise ValueError(f"no digits in reply: {raw!r}")
        try:
            ppm_raw = int(digits)
            # Apply the multiplier fetched during initialization
            ppm_scaled = ppm_raw * self._multiplier
            logging.getLogger(__name__).debug(f"Parsed raw PPM: {ppm_raw}, Multiplier: {self._multiplier}, Scaled PPM: {ppm_scaled}")
            return ppm_scaled
        except ValueError as e:
            logging.getLogger(__name__).warning(f"Could not parse PPM: error converting digits '{digits}' to int: {e}. Raw: {raw!r}")
            raise ValueError(f"Could not convert digits '{digits}' to int from raw: {raw!r}") from e

# Note: The CO2Reading dataclass might be useful elsewhere,
# but the core functionality is in CO2Sensor.
# The usage example is commented out as it's not part of the class definition.
# async def main():
#     async with CO2Sensor() as sensor:
#         print(await sensor.read_ppm())