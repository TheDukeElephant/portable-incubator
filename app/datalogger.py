import aiosqlite
import datetime
import asyncio
import time
import csv
import io
from typing import Optional, Dict, Any, List, Tuple

DEFAULT_DB_PATH = "incubator_log.db"
TABLE_NAME = "logs"

class DataLogger:
    """
    Handles asynchronous logging of incubator data to an SQLite database
    and provides methods for data retrieval.
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

    async def initialize(self):
        """
        Connects to the database and ensures the necessary table exists.
        Must be called before logging data.
        """
        async with self._lock:
            if self._db is None:
                try:
                    self._db = await aiosqlite.connect(self.db_path)
                    await self._db.execute(f"""
                        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                            timestamp REAL PRIMARY KEY,
                            temperature REAL,
                            temperature_sensor1 REAL,
                            temperature_sensor2 REAL,
                            humidity REAL,
                            o2 REAL,
                            co2 REAL,
                            temp_setpoint REAL,
                            humidity_setpoint REAL,
                            o2_setpoint REAL,
                            co2_setpoint REAL
                        )
                    """)
                    await self._db.commit()
                    print(f"DataLogger initialized. Database: {self.db_path}, Table: {TABLE_NAME}")
                except Exception as e:
                    print(f"Error initializing database {self.db_path}: {e}")
                    self._db = None # Ensure db is None if init fails
                    raise # Re-raise the exception

    async def log_data(self, data: Dict[str, Optional[float]]):
        """
        Logs a set of sensor readings and setpoints to the database.

        Args:
            data: A dictionary containing the data points. Expected keys:
                  'temperature', 'temperature_sensor1', 'temperature_sensor2',
                  'humidity', 'o2', 'co2',
                  'temp_setpoint', 'humidity_setpoint', 'o2_setpoint', 'co2_setpoint'.
                  Values should be floats or None.
        """
        if not self._db:
            print("Error: DataLogger not initialized. Cannot log data.")
            return

        # Use current Unix timestamp for logging
        current_timestamp = time.time()

        # Prepare data tuple in the correct order for the SQL query
        # Use None for missing keys or if value is None
        log_entry = (
            current_timestamp,
            data.get('temperature'),
            data.get('temperature_sensor1'),
            data.get('temperature_sensor2'),
            data.get('humidity'),
            data.get('o2'),
            data.get('co2'), # Will be None initially
            data.get('temp_setpoint'),
            data.get('humidity_setpoint'),
            data.get('o2_setpoint'),
            data.get('co2_setpoint') # Will be None initially
        )

        sql = f"""
            INSERT INTO {TABLE_NAME} (
                timestamp, temperature, temperature_sensor1, temperature_sensor2,
                humidity, o2, co2,
                temp_setpoint, humidity_setpoint, o2_setpoint, co2_setpoint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        try:
            async with self._lock: # Ensure atomic write operation
                 if not self._db: # Double check connection after acquiring lock
                     print("Error: DataLogger lost connection before logging.")
                     return
                 await self._db.execute(sql, log_entry)
                 await self._db.commit()
                 # print(f"Data logged at {current_timestamp}") # Optional: for debugging
        except Exception as e:
            print(f"Error logging data: {e}")

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

        # Define CSV headers matching the table structure
        headers = [
            "timestamp", "temperature", "temperature_sensor1", "temperature_sensor2",
            "humidity", "o2", "co2",
            "temp_setpoint", "humidity_setpoint", "o2_setpoint", "co2_setpoint"
        ]

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
            except (TypeError, ValueError, OSError): # Added OSError
                formatted_timestamp = "Invalid Timestamp" # Handle potential errors

            # Create a new list/tuple with the formatted timestamp
            formatted_row = [formatted_timestamp] + list(row[1:])
            writer.writerow(formatted_row)

        return output.getvalue()

    async def get_log_records(self, start_time: Optional[float] = None, end_time: Optional[float] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Returns historical data as a list of dictionaries suitable for JSON responses.

        Keys include: timestamp_iso, timestamp_epoch, temperature, temperature_sensor1,
        temperature_sensor2, humidity, o2, co2, temp_setpoint, humidity_setpoint, o2_setpoint, co2_setpoint.
        """
        rows = await self.get_data(start_time, end_time)
        if rows is None:
            return None
        records: List[Dict[str, Any]] = []
        for row in rows:
            try:
                ts = float(row[0]) if row and row[0] is not None else None
            except (TypeError, ValueError):
                ts = None
            if ts is not None:
                dt_object = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                ts_iso = dt_object.isoformat()
            else:
                ts_iso = None
            records.append({
                "timestamp_iso": ts_iso,
                "timestamp_epoch": ts,
                "temperature": row[1],
                "temperature_sensor1": row[2],
                "temperature_sensor2": row[3],
                "humidity": row[4],
                "o2": row[5],
                "co2": row[6],
                "temp_setpoint": row[7],
                "humidity_setpoint": row[8],
                "o2_setpoint": row[9],
                "co2_setpoint": row[10],
            })
        return records


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
#     data1 = {'temperature': 25.1, 'humidity': 55.2, 'o2': 20.8, 'co2': None,
#              'temp_setpoint': 37.0, 'humidity_setpoint': 60.0, 'o2_setpoint': 20.9, 'co2_setpoint': None}
#     await logger.log_data(data1)
#     await asyncio.sleep(1)
#     data2 = {'temperature': 25.5, 'humidity': 54.8, 'o2': 20.9, 'co2': None,
#              'temp_setpoint': 37.0, 'humidity_setpoint': 60.0, 'o2_setpoint': 20.9, 'co2_setpoint': None}
#     await logger.log_data(data2)
#
#     # Retrieve data
#     print("\nRetrieving all data:")
#     all_data = await logger.get_data()
#     for row in all_data:
#         print(row)
#
#     # Retrieve data as CSV
#     print("\nRetrieving data as CSV:")
#     csv_data = await logger.get_data_as_csv()
#     if csv_data:
#         print(csv_data)
#
#     await logger.close()
#
#     # Example using async with
#     print("\nTesting with async with:")
#     async with DataLogger("test_log2.db") as logger2:
#          await logger2.log_data(data1)
#          csv_data2 = await logger2.get_data_as_csv()
#          print(csv_data2)
#
# if __name__ == '__main__':
#      # Clean up test databases if they exist
#      import os
#      if os.path.exists("test_log.db"): os.remove("test_log.db")
#      if os.path.exists("test_log2.db"): os.remove("test_log2.db")
#
#      asyncio.run(main())
#
#      # Clean up again after run
#      if os.path.exists("test_log.db"): os.remove("test_log.db")
#      if os.path.exists("test_log2.db"): os.remove("test_log2.db")