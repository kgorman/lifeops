# Owner / household context

Copy this file to `~/.config/lifeops/owner_context.md` and edit it with your
own household details. The agent injects it into every prompt so it has the
background it needs to make grounded recommendations.

**This file is read by the agent at runtime — it is intentionally not checked
into the public repo.**

Suggested sections:

- Who lives here, ages, allergies, dietary preferences
- Vehicles and equipment (year/make/model is gold for parts research)
- Properties (primary residence, lake house, etc.) and their location/quirks
- Local vendor preferences (which hardware store, which mechanic)
- Standing constraints ("avoid Amazon when possible", "no calls during 9-5")
- Anything the agent should treat as a hard rule
