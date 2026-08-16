"""Google Places, behind the provider interface.

Thin by design: the HTTP work, key resolution, retries and caching already
live in loom.services.google. This adapts that to `PlacesProvider` and, more
importantly, attaches Google's retention terms to it rather than leaving them
as a comment somewhere in the scout.
"""

import os

from loom.services.google.places import FIELDS_CONTACT, Place, places
from loom.services.places.base import PlaceResult, RetentionPolicy

# Maps Platform ToS 3.2.3: place_id may be stored indefinitely, other Content
# only temporarily. Thirty days is the window the scout has always used.
GOOGLE_CACHE_DAYS = 30


def _to_result(place: Place) -> PlaceResult:
    return PlaceResult(
        provider="google",
        provider_place_id=place.place_id,
        name=place.name,
        address=place.address,
        website=place.website,
        phone=place.phone,
        primary_type=place.primary_type,
        business_status=place.business_status,
        rating=place.rating,
        rating_count=place.rating_count,
        price_level=place.price_level,
        hours=place.hours,
        open_now=place.open_now,
        lat=place.lat,
        lng=place.lng,
        map_uri=place.maps_uri,
        types=place.types,
        raw=place.raw,
    )


class GooglePlacesProvider:
    name = "google"
    # Empty: Google is the fallback everywhere it is not explicitly displaced.
    countries: tuple[str, ...] = ()
    retention = RetentionPolicy(
        cache_days=GOOGLE_CACHE_DAYS,
        durable_fields=("provider", "provider_place_id"),
        terms_url="https://cloud.google.com/maps-platform/terms",
    )

    def configured(self) -> bool:
        return bool(
            os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        )

    async def search(
        self,
        query: str,
        *,
        near: str | None = None,
        radius_m: int = 5000,
        max_results: int = 20,
        language: str | None = None,
        region: str | None = None,
    ) -> list[PlaceResult]:
        found = await places.search_text(
            query,
            near=near,
            radius_m=radius_m,
            max_results=max_results,
            fields=FIELDS_CONTACT,
            language=language,
            region=region,
        )
        return [_to_result(p) for p in found]
