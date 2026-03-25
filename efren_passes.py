from skyfield.api import load, wgs84, EarthSatellite
import requests
import csv

# --- user inputs ---
norad_id = 25544
lat = 32.3199
lon = -106.7637
elevation_m = 1200
start = (2026, 3, 24)
end = (2026, 3, 31)
# -------------------

# get TLE from CelesTrak
url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=TLE"
tle = requests.get(url).text.strip().splitlines()

name = tle[0]
line1 = tle[1]
line2 = tle[2]

ts = load.timescale()
satellite = EarthSatellite(line1, line2, name, ts)
observer = wgs84.latlon(lat, lon, elevation_m=elevation_m)

t0 = ts.utc(*start)
t1 = ts.utc(*end)

times, events = satellite.find_events(observer, t0, t1, altitude_degrees=10.0)

event_names = ['rise', 'peak', 'set']

with open("passes.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["time_utc", "event"])

    for t, e in zip(times, events):
        writer.writerow([t.utc_iso(), event_names[e]])

print("Saved to passes.csv")
