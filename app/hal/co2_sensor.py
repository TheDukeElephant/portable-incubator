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
                 init_cmd: bytes = b'K 2\r\n', read_cmd: bytes = b'Z 2\r\n', *,
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

    async def __aenter__(self):  # async context manager
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
                raw = await asyncio.wait_for(self._reader.readuntil(b'\r'), timeout=1.2)
                logger.info(f"Attempt {attempt + 1}: Received raw data: {raw!r}")
                return self._parse_ppm(raw)

            except asyncio.TimeoutError as exc:
                logger.error(f"Attempt {attempt + 1}: Timeout waiting for CO2 sensor response.")
                last_err = exc
            except ValueError as exc: # Catch parsing errors specifically
                 logger.error(f"Attempt {attempt + 1}: Error parsing CO2 sensor data: {exc}")
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
        logging.getLogger(__name__).debug(f"Sending read command: {self._read_cmd!r}")
        self._writer.write(self._read_cmd)
        await self._writer.drain()
        try:
            # Increased timeout slightly based on original code
            line = await asyncio.wait_for(self._reader.readline(), timeout=1.5)
            logging.getLogger(__name__).debug(f"Received raw data: {line!r}")
            return self._parse_ppm(line)
        except asyncio.TimeoutError:
            logging.getLogger(__name__).error("Timeout waiting for CO2 sensor response.")
            raise
        except Exception as e:
            logging.getLogger(__name__).error(f"Error reading or parsing CO2 sensor data: {e}")
            if attempt == retries - 1:
                logging.getLogger(__name__).error("Max retries reached. Returning 'NC'.")
                return "NC"
            else:
                await asyncio.sleep(retry_delay)


    @staticmethod
    def _parse_ppm(raw: bytes) -> int:
        """
        Accepts:  b'Z 00473\\r'     or  b'Z00473\\r'     or 7‑byte binary frame.
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
            ppm = int(digits)
            logging.getLogger(__name__).debug(f"Parsed PPM: {ppm}")
            return ppm
        except ValueError as e:
            logging.getLogger(__name__).warning(f"Could not parse PPM: error converting digits '{digits}' to int: {e}. Raw: {raw!r}")
            raise ValueError(f"Could not convert digits '{digits}' to int from raw: {raw!r}") from e

# Note: The CO2Reading dataclass might be useful elsewhere,
# but the core functionality is in CO2Sensor.
# The usage example is commented out as it's not part of the class definition.
# async def main():
#     async with CO2Sensor() as sensor:
#         print(await sensor.read_ppm())