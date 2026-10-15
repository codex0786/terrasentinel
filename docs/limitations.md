# Known limitations

These are current, not hypothetical. Remove an item only when a test or documented fix addresses it.

1. **Detection is not a census of fire.** Clouds, smoke, overpass timing, and the sensor's detection
   threshold all cause misses. A label of 0 means "no detection", not "no fire".
2. **Label circularity.** Features and labels both come from FIRMS. A gain shows better prediction of
   *future detections*, not of ground-truth fire. Independent event records have not yet been sourced.
3. **Boundary source and depiction.** The boundary is geoBoundaries gbOpen IND ADM1 (DataMeet / Election
   Commission of India, CC BY 2.5 IN). Its metadata says "2011", but the units reflect the post-2020 layout
   (Telangana, J&K and Ladakh, merged DNH&DD). The extent reaches 37.08°N and covers about 3.18 million km²,
   close to the official 3.29 million km², which suggests the claimed boundary. That has **not** been checked
   against the Survey of India map, so verify it before publishing maps in India.
4. **Border cells.** A 0.1° cell crossing a state border is assigned to the state containing its centre.
   If the centre lies outside India, the cell takes the majority region of its detections.
5. **Science-quality latency assumption.** SP experiments treat data as available immediately. That is
   optimistic, so NRT evaluation is reported separately.
6. **UTC days.** Labels use UTC calendar days (IST = UTC+5:30). A night-time fire around IST
   midnight can fall on a different UTC day than local reporting would suggest.
7. **Lat/lon grid cells are not equal-area.** At 0.1°, cell area shrinks by about 25% from the
   southern tip to the far north.
8. **Sensor outages.** Whole days with no detections for a source (e.g. VIIRS S-NPP, 2024-05-30..06-03)
   are excluded as label days. Trailing features *after* an outage still undercount activity
   (e.g. `fire_count_7d` on 2024-06-05 misses five days). Multi-sensor features would reduce this.
9. **Not a warning system.** TerraSentinel supplements, and does not replace, official warnings
   (IMD, NDMA, state forest departments).
