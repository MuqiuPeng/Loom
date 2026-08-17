"""Check for the Google API component.

Two halves:

  * offline — a stubbed transport exercises parsing, the TTL cache, retry on
    a transient 500, and Google's in-body error statuses. Always runs, so the
    component stays verifiable without spending a billable request.
  * live — only when GOOGLE_MAPS_API_KEY is set: one real geocode round trip,
    which also proves the key, the billing account and the enabled API.

    python -m loom.scripts.check_google_maps

Exits non-zero on any failure.
"""

import asyncio
import json
import os
import sys
from typing import Any

import httpx
from dotenv import load_dotenv

from loom.services.google import client as gclient
from loom.services.google.client import GoogleAPIError
from loom.services.google.geocoding import GeocodingService
from loom.services.google.places import PlacesService

load_dotenv()

PLACES_SAMPLE = {
    "places": [
        {
            "id": "place-with-site",
            "displayName": {"text": "Good Coffee"},
            "formattedAddress": "1 Test St, Sydney NSW",
            "websiteUri": "https://example.com",
            "primaryType": "cafe",
        },
        {
            "id": "place-without-site",
            "displayName": {"text": "Corner Cafe"},
            "formattedAddress": "2 Test St, Sydney NSW",
            "nationalPhoneNumber": "(02) 9000 0000",
            "primaryType": "cafe",
        },
    ]
}

SAMPLE = {
    "status": "OK",
    "results": [
        {
            "formatted_address": "1 Martin Pl, Sydney NSW 2000, Australia",
            "place_id": "ChIJ_____fake",
            "types": ["street_address"],
            "geometry": {
                "location": {"lat": -33.8675, "lng": 151.2070},
                "location_type": "ROOFTOP",
            },
            "address_components": [
                {"long_name": "Sydney", "short_name": "Sydney", "types": ["locality"]},
                {
                    "long_name": "New South Wales",
                    "short_name": "NSW",
                    "types": ["administrative_area_level_1"],
                },
                {"long_name": "Australia", "short_name": "AU", "types": ["country"]},
                {"long_name": "2000", "short_name": "2000", "types": ["postal_code"]},
            ],
        }
    ],
}

failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}")
        failures.append(label)


def install_transport(handler) -> None:
    """Point the shared client at a stub instead of the network."""
    gclient._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def offline_checks() -> None:
    print("offline:")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        check("key=" in str(request.url), "api key is attached to the request")
        return httpx.Response(200, json=SAMPLE)

    install_transport(handler)
    service = GeocodingService(api_key="test-key")

    place = await service.geocode("1 Martin Place, Sydney", components={"country": "AU"})
    check(place is not None, "geocode returns a result")
    assert place is not None
    check((place.lat, place.lng) == (-33.8675, 151.2070), "coordinates parsed")
    check(place.city == "Sydney", "city lifted from address_components")
    check(place.state == "NSW", "state uses the short name")
    check(place.country_code == "AU", "country_code is ISO alpha-2")
    check(place.postal_code == "2000", "postal_code parsed")
    check(place.location_type == "ROOFTOP", "location_type parsed")

    await service.geocode("1 Martin Place, Sydney", components={"country": "AU"})
    check(calls["n"] == 1, "identical lookup is served from cache")
    check(service.stats()["cache_hits"] == 1, "cache hit is counted")

    # Transient failure: first attempt 500, retry succeeds.
    attempts = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(500, text="upstream boom")
        return httpx.Response(200, json=SAMPLE)

    install_transport(flaky)
    retry_service = GeocodingService(api_key="test-key")
    check(await retry_service.geocode("retry me") is not None, "retries a transient 500")
    check(attempts["n"] == 2, "retry took exactly one extra attempt")

    # Hard error: Google reports it in the body with HTTP 200.
    install_transport(
        lambda request: httpx.Response(
            200, json={"status": "REQUEST_DENIED", "error_message": "API key invalid"}
        )
    )
    denied = GeocodingService(api_key="test-key")
    try:
        await denied.geocode("denied")
        check(False, "REQUEST_DENIED raises GoogleAPIError")
    except GoogleAPIError as e:
        check(e.status == "REQUEST_DENIED", "REQUEST_DENIED raises GoogleAPIError")

    # Nothing matched is an answer, not a failure.
    install_transport(lambda request: httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []}))
    empty = GeocodingService(api_key="test-key")
    check(await empty.geocode("nowhere at all") is None, "ZERO_RESULTS returns None")

    # Places (New) is a different shape: POST, key in a header, field mask.
    seen: dict[str, Any] = {}

    def places_handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["key_header"] = request.headers.get("X-Goog-Api-Key")
        seen["mask"] = request.headers.get("X-Goog-FieldMask")
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=PLACES_SAMPLE)

    install_transport(places_handler)
    shops = PlacesService(api_key="test-key")
    results = await shops.search_text("cafe", max_results=5)
    check(seen["method"] == "POST", "places uses POST")
    check(seen["key_header"] == "test-key", "places key travels in X-Goog-Api-Key")
    check("key=" not in seen["url"], "places key is not in the query string")
    check("places.websiteUri" in seen["mask"], "field mask is sent")
    check("nextPageToken" in seen["mask"], "field mask requests the page token")
    check(seen["body"]["textQuery"] == "cafe", "text query is in the body")
    check(len(results) == 2, "both places parsed")
    check(results[0].name == "Good Coffee" and results[0].has_website, "place with a website")
    check(not results[1].has_website, "place without a website is detected")

    # No key configured — callers can degrade instead of crashing.
    os.environ.pop("GOOGLE_MAPS_API_KEY", None)
    os.environ.pop("GOOGLE_API_KEY", None)
    check(not GeocodingService().enabled(), "enabled() is False without a key")

    await gclient.close_http_client()


async def live_check(key: str) -> None:
    print("live:")
    service = GeocodingService(api_key=key)
    try:
        place = await service.geocode("1 Martin Place, Sydney NSW")
    except GoogleAPIError as e:
        # The usual causes: the Geocoding API isn't enabled on the project,
        # no billing account, or the key's API restrictions exclude it.
        check(False, f"live geocode ({e})")
    else:
        check(place is not None, "live geocode returned a result")
        if place:
            print(f"        {place.formatted_address} → {place.lat}, {place.lng}")
    await gclient.close_http_client()


async def main() -> int:
    key = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    await offline_checks()
    if key:
        await live_check(key)
    else:
        print("live: skipped (GOOGLE_MAPS_API_KEY not set)")

    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
