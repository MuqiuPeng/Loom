"""Business-discovery providers, and how a search picks one.

    from loom.services.places import search, provider_for

    results = await search("cafe", near="Katoomba NSW", country="AU")

Selection is by country, because that is what actually decides the answer: a
query about Shanghai is not something Google Maps can usefully answer, and a
query about Katoomba is not something Amap can. A provider declares which
countries it serves; one with no declaration is a fallback.

To add a provider — Amap, Baidu, OpenStreetMap — implement `PlacesProvider`
(see base.py) and append it to `_PROVIDERS`. Nothing else needs to change:
the scout, the area config and the API all go through `search()`.
"""

from loom.services.places.base import (
    PlaceResult,
    PlacesProvider,
    RetentionPolicy,
)
from loom.services.places.google import GooglePlacesProvider

# Order matters only for the fallback: the first provider with no country
# restriction wins when nothing claims the country being searched.
_PROVIDERS: list[PlacesProvider] = [
    GooglePlacesProvider(),
    # Mainland China needs a provider Google cannot be: add an Amap or Baidu
    # implementation here and give it countries=("CN",).
]


class ProviderUnavailableError(RuntimeError):
    """No provider can serve this country, or the one that can has no key."""


def providers() -> list[PlacesProvider]:
    return list(_PROVIDERS)


def provider_for(
    country: str | None = None, *, named: str | None = None
) -> PlacesProvider:
    """The provider that should answer for `country` (ISO-3166-1 alpha-2).

    `named` pins the choice, and is how the area config gets its say. It
    matters most when the named provider does NOT exist yet: a country whose
    config says "amap" must fail loudly rather than fall back, because the
    fallback is Google and Google cannot answer for mainland China. Silently
    returning its results would look like a working search and be nonsense.
    """
    if named:
        for provider in _PROVIDERS:
            if provider.name == named:
                if not provider.configured():
                    raise ProviderUnavailableError(
                        f"places provider {named!r} is registered but not configured"
                    )
                return provider
        raise ProviderUnavailableError(
            f"places provider {named!r} is not implemented — "
            f"available: {', '.join(p.name for p in _PROVIDERS)}"
        )

    code = (country or "").upper()
    if code:
        for provider in _PROVIDERS:
            if code in provider.countries:
                if not provider.configured():
                    raise ProviderUnavailableError(
                        f"{provider.name} serves {code} but is not configured"
                    )
                return provider

    for provider in _PROVIDERS:
        if not provider.countries and provider.configured():
            return provider

    raise ProviderUnavailableError(
        f"No configured places provider for country {code or '(unspecified)'}"
    )


async def search(
    query: str,
    *,
    near: str | None = None,
    radius_m: int = 5000,
    max_results: int = 20,
    country: str | None = None,
    provider_name: str | None = None,
    language: str | None = None,
) -> list[PlaceResult]:
    """Discover businesses, using whichever provider serves `country`."""
    provider = provider_for(country, named=provider_name)
    return await provider.search(
        query,
        near=near,
        radius_m=radius_m,
        max_results=max_results,
        language=language,
        region=(country or None),
    )


__all__ = [
    "ProviderUnavailableError",
    "PlaceResult",
    "PlacesProvider",
    "RetentionPolicy",
    "provider_for",
    "providers",
    "search",
]
