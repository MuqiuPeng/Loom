"""Google Places API (New) — find businesses by text query and area.

Used as a DISCOVERY layer only. Maps Platform ToS (3.2.3) forbids warehousing
Places Content: `place_id` may be stored indefinitely, everything else —
name, address, phone, website, rating — must not be cached beyond 30 days or
turned into your own database. Search, act on the result, drop the detail.

The compliant pattern for building a prospect list lives in
loom/services/company_scout.py: use this module to discover, then take the
durable data from the company's own website, which is not Google Content.

Cost note: the field mask sets the SKU. Asking for websiteUri, phone or rating
moves the call from the Text Search Pro tier to the more expensive Enterprise
tier, so FIELDS_BASIC and FIELDS_CONTACT are kept separate below — use the
cheaper one when you only need to count.

Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
"""

from typing import Any

from pydantic import BaseModel, Field

from loom.services.google.client import GoogleService
from loom.services.google.geocoding import geocoding

# Pro tier — identity and location only.
FIELDS_BASIC = (
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.primaryType",
    "places.businessStatus",
)

# Enterprise tier. Billing is set by the most expensive field in the mask, so
# once websiteUri is in, every other Enterprise field is free — hours, rating,
# price level and location all ride along at the same unit price. Leaving them
# out bought nothing.
#
# Deliberately NOT here: places.reviews and places.editorialSummary sit in the
# pricier Enterprise + Atmosphere tier, and places.photos carries licensing
# terms that rule out the demo use case.
FIELDS_CONTACT = FIELDS_BASIC + (
    "places.websiteUri",
    "places.nationalPhoneNumber",
    "places.rating",
    "places.userRatingCount",
    "places.priceLevel",
    "places.regularOpeningHours",
    "places.location",
    "places.googleMapsUri",
    "places.types",
)

# searchText caps a page at 20 results.
MAX_PAGE_SIZE = 20


class Place(BaseModel):
    """One business from Places.

    Only `place_id` is safe to persist — see the module docstring.
    """

    place_id: str = ""
    name: str = ""
    address: str = ""
    website: str | None = None
    phone: str | None = None
    primary_type: str | None = None
    business_status: str | None = None
    rating: float | None = None
    rating_count: int | None = None
    price_level: str | None = None
    hours: list[str] = Field(default_factory=list)  # one line per weekday
    open_now: bool | None = None
    lat: float | None = None
    lng: float | None = None
    maps_uri: str | None = None
    types: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @property
    def has_website(self) -> bool:
        return bool(self.website)

    @classmethod
    def from_result(cls, result: dict[str, Any]) -> "Place":
        hours = result.get("regularOpeningHours", {})
        location = result.get("location", {})
        return cls(
            place_id=result.get("id", ""),
            name=result.get("displayName", {}).get("text", ""),
            address=result.get("formattedAddress", ""),
            website=result.get("websiteUri"),
            phone=result.get("nationalPhoneNumber"),
            primary_type=result.get("primaryType"),
            business_status=result.get("businessStatus"),
            rating=result.get("rating"),
            rating_count=result.get("userRatingCount"),
            price_level=result.get("priceLevel"),
            hours=hours.get("weekdayDescriptions", []),
            open_now=hours.get("openNow"),
            lat=location.get("latitude"),
            lng=location.get("longitude"),
            maps_uri=result.get("googleMapsUri"),
            types=result.get("types", []),
            raw=result,
        )


class PlacesService(GoogleService):
    """Text search over Google's business index."""

    name = "places"
    base_url = "https://places.googleapis.com/v1"
    key_in_header = True  # v1 APIs want X-Goog-Api-Key

    async def search_text(
        self,
        query: str,
        *,
        near: str | None = None,
        radius_m: int = 5000,
        max_results: int = 20,
        fields: tuple[str, ...] = FIELDS_CONTACT,
        language: str | None = None,
        region: str | None = None,
    ) -> list[Place]:
        """Businesses matching `query`, optionally biased to an area.

        `near` is a free-text place ("Surry Hills, Sydney") — it is geocoded
        first and used as a circular bias, which is far more precise than
        stuffing the suburb into the query string. That geocode is one extra
        billable call, cached for 24h.
        """
        query = (query or "").strip()
        if not query:
            return []

        body: dict[str, Any] = {
            "textQuery": query,
            "pageSize": min(max_results, MAX_PAGE_SIZE),
        }
        if language:
            body["languageCode"] = language
        if region:
            body["regionCode"] = region
        if near:
            centre = await geocoding.geocode(near)
            if centre:
                # Restriction, not bias. Bias is a preference Google is free to
                # overrule, and it does: a search for espresso bars around a
                # NSW suburb returned a shop in Wilmington, Delaware, because
                # the name matched strongly enough to outweigh the geography.
                # regionCode does not help — it formats and ranks, and the API
                # documents that it does not restrict. This is the only
                # parameter that actually means "not outside here".
                body["locationRestriction"] = {
                    "circle": {
                        "center": {"latitude": centre.lat, "longitude": centre.lng},
                        "radius": float(radius_m),
                    }
                }

        # nextPageToken has to be requested explicitly or paging can't work.
        mask = ",".join((*fields, "nextPageToken"))

        places: list[Place] = []
        while len(places) < max_results:
            payload = await self.request(
                "/places:searchText",
                method="POST",
                body=body,
                headers={"X-Goog-FieldMask": mask},
                action="search_text",
            )
            places.extend(Place.from_result(r) for r in payload.get("places", []))
            token = payload.get("nextPageToken")
            if not token:
                break
            body = {**body, "pageToken": token}

        return places[:max_results]


# Process-wide instance — shares one cache and one set of counters.
places = PlacesService()


async def search_places(
    query: str,
    *,
    near: str | None = None,
    radius_m: int = 5000,
    max_results: int = 20,
    fields: tuple[str, ...] = FIELDS_CONTACT,
) -> list[Place]:
    """Module-level shortcut for the shared PlacesService."""
    return await places.search_text(
        query, near=near, radius_m=radius_m, max_results=max_results, fields=fields
    )
