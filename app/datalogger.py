import aiosqlite
import datetime
import asyncio
import time
import csv
import io
from typing import Optional, Dict, Any, List, Tuple
import os # Added for checking file existence

# --- Constants ---
DEFAULT_DB_PATH = "incubator_log.db"
TABLE_NAME = "logs"
LOCAL_LOG_FILE = "local_data_log.csv" # Path for offline CSV log

# --- Column Headers (consistent order for DB and CSV) ---
LOG_HEADERS = [
    "timestamp", "temperature", "humidity", "o2", "co2",
    "temp_setpoint", "humidity_setpoint", "o2_setpoint", "co2_setpoint"
]

# --- Placeholder for network status ---
def is_offline() -> bool:
    """Placeholder function to simulate offline status."""
    # In a real implementation, this would check network connectivity.
    # For now, always return True to test local logging.
    return True

class DataLogger:
    """
    Handles asynchronous logging of incubator data to an SQLite database
    and provides methods for data retrieval. Also handles offline logging to CSV.
    """
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initializes the DataLogger.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock() # To prevent concurrent writes during initialization
        self.local_log_file = LOCAL_LOG_FILE # Store local log path

    async def initialize(self):
        """
        Connects to the database and ensures the necessary table exists.
        Must be called before logging data.
        """
        async with self._lock:
            if self._db is None:
                try:
                    self._db = await aiosqlite.connect(self.db_path)
                    # Use LOG_HEADERS to define table columns dynamically
                    # Ensure timestamp is PRIMARY KEY
                    columns_sql_parts = [f"{LOG_HEADERS[0]} REAL PRIMARY KEY"]
                    columns_sql_parts.extend([f"{col} REAL" for col in LOG_HEADERS[1:]])
                    columns_sql = ",\n                            ".join(columns_sql_parts)

                    await self._db.execute(f"""
                        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                            {columns_sql}
                        )
                    """)
                    await self._db.commit()
                    print(f"DataLogger initialized. Database: {self.db_path}, Table: {TABLE_NAME}")
                except Exception as e:
                    print(f"Error initializing database {self.db_path}: {e}")
                    self._db = None # Ensure db is None if init fails
                    raise # Re-raise the exception

    # --- Internal Methods ---
    def _log_to_csv(self, data: Dict[str, Optional[float]], timestamp: float):
        """Logs data to the local CSV file."""
        file_exists = os.path.isfile(self.local_log_file)
        try:
            # Convert timestamp to ISO format string for readability
            try:
                dt_object = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
                formatted_timestamp = dt_object.isoformat()
            except (TypeError, ValueError):
                formatted_timestamp = str(timestamp) # Fallback to raw timestamp if conversion fails

            # Prepare data row in the correct order using LOG_HEADERS
            # Ensure timestamp is the first element
            log_entry = [formatted_timestamp] + [data.get(header) for header in LOG_HEADERS[1:]]

            with open(self.local_log_file, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                if not file_exists or os.path.getsize(self.local_log_file) == 0:
                    writer.writerow(LOG_HEADERS) # Write header if file is new or empty
                writer.writerow(log_entry)
            # print(f"Data logged locally to {self.local_log_file}") # Optional debug
        except IOError as e:
            print(f"Error writing to local log file {self.local_log_file}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during local logging: {e}")

    # --- Public API ---
    async def log_data(self, data: Dict[str, Optional[float]]):
        """
        Logs a set of sensor readings and setpoints.
        If offline (determined by is_offline()), logs to a local CSV file.
        If online, logs to the SQLite database.

        Args:
            data: A dictionary containing the data points. Expected keys match LOG_HEADERS (excluding timestamp).
                  Values should be floats or None.
        """
        # Use current Unix timestamp for logging
        current_timestamp = time.time()

        # --- Offline Logging Check ---
        if is_offline():
            # Use synchronous file I/O for simplicity here.
            # Consider aiofiles if this becomes a bottleneck.
            self._log_to_csv(data, current_timestamp)
            # If offline, we log locally. We skip database logging as per requirement.
            return # Skip database logging if offline

        # --- Online (Database) Logging ---
        if not self._db:
            print("Error: DataLogger not initialized. Cannot log data to database.")
            # Optional: Could add fallback to local CSV logging here too if DB fails even when "online"
            return

        # Prepare data tuple in the correct order for the SQL query using LOG_HEADERS
        # Ensure timestamp is the first element
        log_entry = tuple([current_timestamp] + [data.get(header) for header in LOG_HEADERS[1:]])

        sql = f"""
            INSERT INTO {TABLE_NAME} ({', '.join(LOG_HEADERS)})
            VALUES ({', '.join(['?'] * len(LOG_HEADERS))})
        """

        try:
            async with self._lock: # Ensure atomic write operation
                 if not self._db: # Double check connection after acquiring lock
                     print("Error: DataLogger lost connection before logging.")
                     return
                 await self._db.execute(sql, log_entry)
                 await self._db.commit()
                 # print(f"Data logged to DB at {current_timestamp}") # Optional: for debugging
        except Exception as e:
            print(f"Error logging data to database: {e}")

    async def get_data(self, start_time: Optional[float] = None, end_time: Optional[float] = None) -> List[Tuple]:
        """
        Retrieves logged data, optionally filtered by a time range.

        Args:
            start_time: Optional start timestamp (Unix timestamp).
            end_time: Optional end timestamp (Unix timestamp).

        Returns:
            A list of tuples, where each tuple represents a row from the database.
            Returns an empty list if an error occurs or no data is found.
        """
        if not self._db:
            print("Error: DataLogger not initialized. Cannot retrieve data.")
            return []

        query = f"SELECT * FROM {TABLE_NAME}"
        params = []
        conditions = []

        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp ASC" # Ensure chronological order

        try:
            async with self._db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return rows
        except Exception as e:
            print(f"Error retrieving data: {e}")
            return []

    async def get_data_as_csv(self, start_time: Optional[float] = None, end_time: Optional[float] = None) -> Optional[str]:
        """
        Retrieves logged data as a CSV formatted string.

        Args:
            start_time: Optional start timestamp (Unix timestamp).
            end_time: Optional end timestamp (Unix timestamp).

        Returns:
            A string containing the data in CSV format, including headers,
            or None if an error occurs or no data is found.
        """
        rows = await self.get_data(start_time, end_time)
        if not rows:
            return None # No data or error occurred

        # Use the constant for headers
        headers = LOG_HEADERS

        # Use io.StringIO to write CSV data to a string buffer
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(headers)
        # Convert timestamp and write rows
        for row in rows:
            # Convert Unix timestamp (first element) to ISO 8601 string
            try:
                # Assuming row[0] is the timestamp
                dt_object = datetime.datetime.fromtimestamp(row[0], tz=datetime.timezone.utc)
                formatted_timestamp = dt_object.isoformat()
            except (TypeError, ValueError):
                formatted_timestamp = "Invalid Timestamp" # Handle potential errors

            # Create a new list/tuple with the formatted timestamp
            formatted_row = [formatted_timestamp] + list(row[1:])
            writer.writerow(formatted_row)

        return output.getvalue()


    async def close(self):
        """Closes the database connection."""
        async with self._lock:
            if self._db:
                try:
                    await self._db.close()
                    print("DataLogger database connection closed.")
                except Exception as e:
                    print(f"Error closing database connection: {e}")
                finally:
                    self._db = None

    async def __aenter__(self):
        """Allows using 'async with DataLogger(...)' syntax."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensures connection is closed when exiting 'async with' block."""
        await self.close()

# Example Usage (Conceptual - requires running within an asyncio loop)
# async def main():
#     logger = DataLogger("test_log.db")
#     await logger.initialize()
#
#     # Simulate logging some data
#     # Ensure data keys match LOG_HEADERS (excluding timestamp)
#     data1 = {'temperature': 25.1, 'humidity': 55.2, 'o2': 20.8, 'co2': None,
#              'temp_setpoint': 37.0, 'humidity_setpoint': 60.0, 'o2_setpoint': 20.9, 'co2_setpoint': None}
#     await logger.log_data(data1)
#     await asyncio.sleep(1) # Give time for potential file write
#     data2 = {'temperature': 25.5, 'humidity': 54.8, 'o2': 20.9, 'co2': None,
#              'temp_setpoint': 37.0, 'humidity_setpoint': 60.0, 'o2_setpoint': 20.9, 'co2_setpoint': None}
#     await logger.log_data(data2)
#
#     # Retrieve data (will be empty if always offline)
#     print("\nRetrieving all data from DB:")
#     all_data = await logger.get_data()
#     for row in all_data:
#         print(row)
#
#     # Retrieve data as CSV (will be empty if always offline)
#     print("\nRetrieving data as CSV from DB:")
#     csv_data = await logger.get_data_as_csv()
#     if csv_data:
#         print(csv_data)
#     else:
#         print("No data in DB to retrieve as CSV.")
#
#     await logger.close()
#     print(f"\nCheck '{LOCAL_LOG_FILE}' for locally logged data.")
#
#     # Example using async with
#     # print("\nTesting with async with:")
#     # async with DataLogger("test_log2.db") as logger2:
#     #      await logger2.log_data(data1)
#     #      csv_data2 = await logger2.get_data_as_csv()
#     #      print(csv_data2)
#
# if __name__ == '__main__':
#      # Clean up test databases and local log if they exist
#      # Need to import os here if running this block directly
#      import os
#      if os.path.exists(DEFAULT_DB_PATH): os.remove(DEFAULT_DB_PATH) # Use constant
#      if os.path.exists("test_log.db"): os.remove("test_log.db") # Example db
