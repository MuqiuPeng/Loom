"""The seam between "find businesses near here" and whoever answers that.

Discovery used to be Google Places called directly from company_scout. That
worked while the only market was Australia, and stops working the moment the
answer is "it depends where you are asking about": Google Maps is unusable in
mainland China, where the equivalent question goes to Amap or Baidu, and each
provider comes with its own terms about what may be kept.

That last part is why this is an interface rather than a function. Google's
Maps Platform terms (ToS 3.2.3) let you store the place_id indefinitely and
essentially nothing else — names, addresses and phone numbers are Content and
must expire. A different provider has different rules, and hard-coding
Google's into the scout would quietly apply them to data they don't govern,
or worse, fail to apply them to data they do. So retention travels with the
provider, and callers ask the provider what they are allowed to keep.

Adding a provider means implementing `PlacesProvider` and registering it. The
scout, the area config and the API do not change.
"""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class PlaceResult(BaseModel):
    """One discovered business, in provider-neutral shape.

    `provider` + `provider_place_id` together identify a business. The pair
    matters: the same café has a different id in Google and in Amap, and a
    lead saved from one is not the same row as a lead saved from the other.
    """

    provider: str
    provider_place_id: str

    name: str = ""
    address: str = ""
    website: str | None = None
    phone: str | None = None
    primary_type: str | None = None
    business_status: str | None = None
    rating: float | None = None
    rating_count: int | None = None
    price_level: str | None = None
    hours: list[str] = Field(default_factory=list)
    open_now: bool | None = None
    lat: float | None = None
    lng: float | None = None
    map_uri: str | None = None
    types: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @property
    def has_website(self) -> bool:
        return bool(self.website)


class RetentionPolicy(BaseModel):
    """What a provider permits its caller to keep, and for how long.

    `cache_days=None` means the provider-sourced fields may be kept
    indefinitely. Anything else is a ceiling the caller must honour by
    blanking those fields once past it — which is what `google_expires_at` on
    scout_leads does today.
    """

    cache_days: int | None = None
    # Fields exempt from expiry — the stable identifier, normally.
    durable_fields: tuple[str, ...] = ("provider", "provider_place_id")
    # Human-readable pointer to the terms, so the reason is one click away
    # rather than folklore.
    terms_url: str | None = None


@runtime_checkable
class PlacesProvider(Protocol):
    """A source of "businesses matching this query, near this place"."""

    name: str
    #: ISO-3166-1 alpha-2 codes this provider is appropriate for. Empty means
    #: "no restriction" — used as the fallback when no provider claims a
    #: country.
    countries: tuple[str, ...]
    retention: RetentionPolicy

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
        ...

    def configured(self) -> bool:
        """Whether this provider has the credentials it needs."""
        ...
