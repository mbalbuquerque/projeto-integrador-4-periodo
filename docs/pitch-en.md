# Pitch (2 minutes, English)

Speaker notes for the opening pitch. Slides: at most 6.

## Script

**Problem.** Fruit from the São Francisco Valley, like mango and grapes, travels for hours in
refrigerated trucks. If the temperature leaves the safe range, the cargo can be lost, and the
driver and the company often find out only when the truck arrives.

**Solution.** ColdTrack is a sensor node plus a web dashboard. An ESP32-C3 reads temperature and
humidity inside the cargo area, classifies each reading against the range for that cargo, shows the
status with LEDs or a small screen, and sends it to the cloud every 20 seconds.

**How it works.** The device sends each reading over HTTPS to an API on Azure Functions. The
readings are stored in Cosmos DB, and the web dashboard, installable as a PWA, shows the current
state, the history and the alerts of each company. If the network drops, the device keeps the
readings in flash memory and sends them again when it reconnects, with the original measurement time.

**Why it is safe.** Each sensor has its own key, each company only sees its own data, and every
request goes through HTTPS and a signed token.

**Value.** The team sees a problem while the truck is still on the road, not after the cargo is lost.

## Slides (6)

1. Problem: cold chain in fruit transport.
2. Solution: ColdTrack in one sentence and one photo of the device.
3. Architecture: device → HTTPS → Azure Functions → Cosmos DB → dashboard (diagram).
4. Live demo: stimulus, reading, dashboard, alert.
5. Resilience and security: offline queue, keys per sensor, isolation by company.
6. Next steps: from the action plan.

## Questions to prepare (from the exam bank)

- "Walk us through what happens when the sensor reading crosses the alert threshold."
- "What was the hardest trade-off in your architecture, and why?"
