"""Google API integration — a standalone component.

Two layers:

    client.py     shared plumbing every Google API needs — API key, pooled
                  httpx client, retry/backoff, TTL cache, Loom log entries
    geocoding.py  one module per API; the reference implementation

Adding another Google API (Places, Routes, Distance Matrix, ...) means adding
one module that subclasses GoogleService — no changes to the plumbing.

Configure with GOOGLE_MAPS_API_KEY (falls back to GOOGLE_API_KEY).
"""

from loom.services.google.client import (
    GoogleAPIError,
    GoogleNotConfiguredError,
    GoogleService,
    close_http_client,
)
from loom.services.google.geocoding import (
    GeocodingService,
    GeoLocation,
    geocode,
    geocoding,
    reverse_geocode,
)
from loom.services.google.places import (
    Place,
    PlacesService,
    places,
    search_places,
)

__all__ = [
    "GeoLocation",
    "GeocodingService",
    "GoogleAPIError",
    "GoogleNotConfiguredError",
    "GoogleService",
    "Place",
    "PlacesService",
    "close_http_client",
    "geocode",
    "geocoding",
    "places",
    "reverse_geocode",
    "search_places",
]
