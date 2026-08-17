"""Google Geocoding API — address ⇄ coordinates.

The reference implementation of a Google service module: only what is specific
to this API lives here (endpoint, parameters, response shape). Key handling,
retries, caching and logging come from GoogleService.

    from loom.services.google import geocode

    place = await geocode("1 Martin Place, Sydney")
    if place:
        print(place.lat, place.lng, place.city, place.country_code)

Docs: https://developers.google.com/maps/documentation/geocoding
"""

from typing import Any

from pydantic import BaseModel, Field

from loom.services.google.client import GoogleService

# Google's address_components are a flat list of typed parts; these are the
# types we lift into named fields, most specific first.
_CITY_TYPES = ("locality", "postal_town", "sublocality", "administrative_area_level_2")


class GeoLocation(BaseModel):
    """One geocoding result, flattened to the fields callers actually use."""

    formatted_address: str = ""
    lat: float = 0.0
    lng: float = 0.0
    place_id: str | None = None
    # ROOFTOP | RANGE_INTERPOLATED | GEOMETRIC_CENTER | APPROXIMATE —
    # how precise the coordinates are.
    location_type: str | None = None
    partial_match: bool = False
    city: str | None = None
    state: str | None = None  # short form, e.g. "NSW"
    country: str | None = None
    country_code: str | None = None  # ISO 3166-1 alpha-2
    postal_code: str | None = None
    types: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @classmethod
    def from_result(cls, result: dict[str, Any]) -> "GeoLocation":
        location = result.get("geometry", {}).get("location", {})
        components = result.get("address_components", [])

        def pick(*wanted: str, short: bool = False) -> str | None:
            for want in wanted:
                for component in components:
                    if want in component.get("types", []):
                        return component.get("short_name" if short else "long_name")
            return None

        return cls(
            formatted_address=result.get("formatted_address", ""),
            lat=location.get("lat", 0.0),
            lng=location.get("lng", 0.0),
            place_id=result.get("place_id"),
            location_type=result.get("geometry", {}).get("location_type"),
            partial_match=bool(result.get("partial_match")),
            city=pick(*_CITY_TYPES),
            state=pick("administrative_area_level_1", short=True),
            country=pick("country"),
            country_code=pick("country", short=True),
            postal_code=pick("postal_code"),
            types=result.get("types", []),
            raw=result,
        )


class GeocodingService(GoogleService):
    """Address → coordinates, and back."""

    name = "geocoding"
    base_url = "https://maps.googleapis.com/maps/api/geocode"

    async def geocode(
        self,
        address: str,
        *,
        region: str | None = None,
        language: str | None = None,
        components: dict[str, str] | None = None,
    ) -> GeoLocation | None:
        """Best match for a free-text address, or None if nothing matched.

        `region` is a ccTLD bias ("au", "cn"); `components` is a hard filter,
        e.g. {"country": "AU"} to reject matches outside Australia.
        """
        results = await self.geocode_all(
            address, region=region, language=language, components=components
        )
        return results[0] if results else None

    async def geocode_all(
        self,
        address: str,
        *,
        region: str | None = None,
        language: str | None = None,
        components: dict[str, str] | None = None,
    ) -> list[GeoLocation]:
        """Every candidate Google returns, best first."""
        address = (address or "").strip()
        if not address:
            return []
        payload = await self.request(
            "/json",
            params={
                "address": address,
                "region": region,
                "language": language,
                "components": _components(components),
            },
            action="geocode",
        )
        return [GeoLocation.from_result(r) for r in payload.get("results", [])]

    async def reverse(
        self,
        lat: float,
        lng: float,
        *,
        language: str | None = None,
        result_type: str | None = None,
    ) -> GeoLocation | None:
        """Coordinates → the most precise address Google has for them."""
        payload = await self.request(
            "/json",
            params={
                "latlng": f"{lat},{lng}",
                "language": language,
                "result_type": result_type,
            },
            action="reverse_geocode",
        )
        results = payload.get("results", [])
        return GeoLocation.from_result(results[0]) if results else None


def _components(components: dict[str, str] | None) -> str | None:
    """{"country": "AU", "locality": "Sydney"} → "country:AU|locality:Sydney"."""
    if not components:
        return None
    return "|".join(f"{k}:{v}" for k, v in components.items())


# Process-wide instance — shares one cache and one set of counters.
geocoding = GeocodingService()


async def geocode(
    address: str,
    *,
    region: str | None = None,
    language: str | None = None,
    components: dict[str, str] | None = None,
) -> GeoLocation | None:
    """Module-level shortcut for the shared GeocodingService."""
    return await geocoding.geocode(
        address, region=region, language=language, components=components
    )


async def reverse_geocode(
    lat: float,
    lng: float,
    *,
    language: str | None = None,
) -> GeoLocation | None:
    """Module-level shortcut for the shared GeocodingService."""
    return await geocoding.reverse(lat, lng, language=language)
