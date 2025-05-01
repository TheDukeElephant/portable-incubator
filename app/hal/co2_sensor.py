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
    def __init__(self, port='/dev/serial0', baudrate=9600,
                 init_cmd=b'K 2\r\n', read_cmd=b'Z 2\r\n', *,
                 timeout=1.0):
        self._port_cfg = dict(port=port, baudrate=baudrate, timeout=timeout)
        self._init_cmd = init_cmd
        self._read_cmd = read_cmd
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def __aenter__(self):  # async context manager
        self._reader, self._writer = await serial_asyncio.open_serial_connection(**self._port_cfg)
        # Original code had drain/sleep here, but open_serial_connection likely handles readiness.
        # Let's keep it simple unless issues arise.
        # await self._writer.drain()
        # await asyncio.sleep(0.1)
        if self._init_cmd:
            logging.getLogger(__name__).info(f"Sending init command: {self._init_cmd!r}")
            self._writer.write(self._init_cmd)
            await self._writer.drain()
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
        retries = 3
        retry_delay = 0.5

        for attempt in range(retries):
            try:
                if not self._writer or not self._reader:
                    logging.getLogger(__name__).warning(f"Attempt {attempt + 1}: Sensor connection not established or closed.")
                    if attempt == retries - 1:
                        logging.getLogger(__name__).error("Max retries reached. Attempting to reinitialize sensor connection.")
                        try:
                            await self.__aenter__()
                            logging.getLogger(__name__).info("Sensor connection reinitialized successfully.")
                        except Exception as e:
                            logging.getLogger(__name__).error(f"Sensor reinitialization failed: {e}")
                            return "NC"
                    await asyncio.sleep(retry_delay)
                    continue

                logging.getLogger(__name__).debug(f"Sending read command: {self._read_cmd!r}")
                self._writer.write(self._read_cmd)
                await self._writer.drain()
                line = await asyncio.wait_for(self._reader.readline(), timeout=1.5)
                logging.getLogger(__name__).debug(f"Received raw data: {line!r}")
                return self._parse_ppm(line)

            except asyncio.TimeoutError:
                logging.getLogger(__name__).error(f"Attempt {attempt + 1}: Timeout waiting for CO2 sensor response.")
            except Exception as e:
                logging.getLogger(__name__).error(f"Attempt {attempt + 1}: Error reading or parsing CO2 sensor data: {e}")

            if attempt < retries - 1:
                await asyncio.sleep(retry_delay)

        logging.getLogger(__name__).error("Max retries reached. Returning 'NC'.")
        return "NC"
                    continue
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
                break


    @staticmethod
    def _parse_ppm(raw: bytes) -> int:
        try:
            # Expect "Z 1234\r\n" or similar based on read_cmd
            decoded = raw.decode('ascii', errors='ignore').strip()
            parts = decoded.split()
            if not parts:
                 raise ValueError("Empty response received")
            # Assuming the value is the last part
            value_str = parts[-1]
            # Check if the prefix matches the expected response format if needed
            # e.g., if self._read_cmd is b'Z\r\n', expect prefix 'Z'
            # prefix = parts[0]
            # assert prefix == 'Z' # Or adapt based on actual command/response
            ppm = int(value_str)
            logging.getLogger(__name__).debug(f"Parsed PPM: {ppm}")
            return ppm
        except (ValueError, IndexError, UnicodeDecodeError) as e:
            logging.getLogger(__name__).warning(f"Bad frame format: {raw!r} ({e})")
            raise ValueError(f"Could not parse PPM value from sensor response: {raw!r}") from e
        except Exception as e:
            logging.getLogger(__name__).error(f"Unexpected error parsing PPM: {raw!r} ({e})")
            raise

# Note: The CO2Reading dataclass might be useful elsewhere,
# but the core functionality is in CO2Sensor.
# The usage example is commented out as it's not part of the class definition.
# async def main():
#     async with CO2Sensor() as sensor:
#         print(await sensor.read_ppm())