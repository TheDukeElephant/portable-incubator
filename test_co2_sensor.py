import asyncio
from app.hal.co2_sensor import CO2Sensor

async def main():
    print("Starting CO2 sensor test...")
    sensor_port = "/dev/ttyS0"
    try:
        async with CO2Sensor(sensor_port) as sensor:
            co2_ppm = await sensor.read_ppm()
            print(f"CO2 PPM: {co2_ppm}")
    except Exception as e:
        print(f"Failed to read from CO2 sensor: {e}")

if __name__ == "__main__":
    asyncio.run(main())