import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from config import settings
from models.Task import TaskCache
from parsers.base import BaseParser, ParsedListing

logger = logging.getLogger(__name__)


class YoulaParser(BaseParser):
    platform = "youla"

    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    async def parse(self, task: TaskCache) -> list[ParsedListing]:
        return await asyncio.to_thread(self._parse_sync, task.url)

    def _parse_sync(self, url: str) -> list[ParsedListing]:
        response = requests.get(
            url,
            headers=self._headers(url),
            cookies=settings.youla_cookies,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        state = self._extract_state(response.text)
        listings = self._parse_product_cards(soup)
        if not listings:
            listings = self._parse_embedded_links(soup)
        if not listings:
            listings = self._parse_graphql_feed(url, state)
        if not listings:
            self._log_empty_response(url, response, soup)

        logger.info("Parsed %s Youla listings from %s", len(listings), url)
        return listings

    def _extract_state(self, html: str) -> dict | None:
        match = re.search(r"window\.__YOULA_STATE__\s*=\s*(\{.*?\});\s*window\.__YOULA_TEST__", html, re.S)
        if not match:
            return None

        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("Failed to decode __YOULA_STATE__ from Youla page")
            return None

    def _parse_graphql_feed(self, url: str, state: dict | None) -> list[ParsedListing]:
        if not state:
            return []

        endpoint = (((state.get("auth") or {}).get("apiFederationUri")) or "").replace("\\/", "/")
        if not endpoint:
            endpoint = "https://api-gw.youla.ru/graphql"

        payload = self._graphql_payload(url, state)
        headers = self._graphql_headers(url, state)

        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                cookies=settings.youla_cookies,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Youla GraphQL fallback failed for %s: %s", url, exc)
            return []

        if data.get("errors"):
            logger.warning("Youla GraphQL returned errors for %s: %s", url, data["errors"])
            return []

        items = (((data.get("data") or {}).get("feed") or {}).get("items")) or []
        listings = []
        for item in items:
            product = item.get("product") if isinstance(item, dict) else None
            if not isinstance(product, dict):
                continue

            absolute_url = self._normalize_url(product.get("url"))
            external_id = str(product.get("id") or self._id_from_url(absolute_url) or "")
            title = product.get("name")
            if not absolute_url or not external_id or not title:
                continue

            image_url = None
            images = product.get("images")
            if isinstance(images, list) and images:
                first = images[0]
                if isinstance(first, dict):
                    image_url = first.get("url")

            price = None
            price_info = product.get("price")
            if isinstance(price_info, dict):
                real_price = price_info.get("realPrice")
                orig_price = price_info.get("origPrice")
                if isinstance(real_price, dict):
                    price = self._parse_price(real_price.get("price"))
                if price is None and isinstance(orig_price, dict):
                    price = self._parse_price(orig_price.get("price"))
                if price is None:
                    price = self._parse_price(price_info.get("realPriceText"))

            listings.append(
                ParsedListing(
                    platform=self.platform,
                    external_id=external_id,
                    title=str(title),
                    price=price,
                    url=absolute_url,
                    image_url=image_url,
                )
            )

        return self._deduplicate(listings)

    def _graphql_headers(self, url: str, state: dict) -> dict[str, str]:
        auth = state.get("auth") or {}
        uid = str(auth.get("uid") or "")
        token = auth.get("token")
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "origin": "https://youla.ru",
            "referer": url,
            "user-agent": settings.youla_user_agent,
            "x-app-id": str(auth.get("apiClientId") or "web/3"),
        }
        if uid:
            headers["x-uid"] = uid
            headers["uid"] = uid
        if auth.get("abSplits"):
            headers["x-youla-splits"] = str(auth["abSplits"])
        if auth.get("csrfToken"):
            headers["x-csrf-token"] = str(auth["csrfToken"])
        if token:
            headers["authorization"] = str(token)
        return headers

    def _graphql_payload(self, url: str, state: dict) -> dict:
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        city_id = self._city_id_from_state(url, state)
        search = (params.get("q") or [""])[0]
        sort = self._graphql_sort(params)
        category_slug = self._category_slug_from_url(url, state)

        attributes = []
        if category_slug:
            attributes.append(
                {
                    "slug": "categories",
                    "value": [category_slug],
                    "from": None,
                    "to": None,
                }
            )

        return {
            "operationName": "catalogProductsBoard",
            "variables": {
                "sort": sort,
                "attributes": attributes,
                "datePublished": None,
                "location": {
                    "latitude": None,
                    "longitude": None,
                    "city": city_id,
                    "distanceMax": None,
                },
                "search": search,
                "cursor": "",
            },
            "query": """
query catalogProductsBoard($sort: Sort, $attributes: [AttributeItem!], $location: LocationInput, $cursor: Cursor!, $search: String, $datePublished: DateInput) {
  feed(input: {sort: $sort, attributes: $attributes, location: $location, search: $search, datePublished: $datePublished}, after: $cursor) {
    items {
      ... on PromotedProductItem {
        product: productPromoted {
          ...ProductCardFragment
        }
      }
      ... on ProductItem {
        product {
          ...ProductCardFragment
        }
      }
    }
  }
}

fragment ProductCardFragment on Product {
  id
  url
  name
  images {
    url
  }
  price {
    origPrice {
      price
    }
    realPrice {
      price
    }
    realPriceText
  }
}
""".strip(),
        }

    def _graphql_sort(self, params: dict[str, list[str]]) -> str:
        sort_field = (params.get("attributes[sort_field]") or [""])[0]
        if sort_field == "date_published":
            return "DATE_PUBLISHED_DESC"
        return "DEFAULT"

    def _city_id_from_state(self, url: str, state: dict) -> str | None:
        city_slug = self._city_slug_from_url(url, state)
        for city in self._known_cities(state):
            if str(city.get("slug") or "") == city_slug and city.get("id"):
                return str(city["id"])

        auth = state.get("auth") or {}
        geo_params = ((auth.get("geoLocation") or {}).get("params")) or {}
        if geo_params.get("id"):
            return str(geo_params["id"])
        return None

    def _city_slug_from_url(self, url: str, state: dict) -> str | None:
        route_params = ((state.get("data") or {}).get("routeParams")) or {}
        route_city = route_params.get("citySlug")
        if route_city:
            return str(route_city)

        parts = [part for part in urlsplit(url).path.split("/") if part]
        if parts and parts[0] != "all":
            return parts[0]
        return None

    def _category_slug_from_url(self, url: str, state: dict) -> str | None:
        parts = [part for part in urlsplit(url).path.split("/") if part]
        city_slug = self._city_slug_from_url(url, state)
        if city_slug and parts and parts[0] == city_slug:
            parts = parts[1:]
        elif parts and parts[0] == "all":
            parts = parts[1:]

        if not parts:
            return None

        last = parts[-1]
        if re.search(r"-[0-9a-f]{20,32}$", last, re.IGNORECASE):
            return None
        return last

    def _known_cities(self, state: dict) -> list[dict]:
        entities = state.get("entities") or {}
        data = state.get("data") or {}
        cities = []
        for source in (entities.get("cities"), data.get("cities")):
            if isinstance(source, list):
                cities.extend(city for city in source if isinstance(city, dict))
        return cities

    def _headers(self, url: str) -> dict[str, str]:
        return {
            "accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
                "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
            ),
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "max-age=0",
            "connection": "keep-alive",
            "host": "youla.ru",
            "referer": url,
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": settings.youla_user_agent,
        }

    def _parse_product_cards(self, soup: BeautifulSoup) -> list[ParsedListing]:
        listings = []
        for card in soup.select("[data-test-component='ProductOrAdCard']"):
            figure = card.select_one("[data-test-component='ProductCard']")
            link = card.select_one("a[href]")
            href = link.get("href") if link else None
            absolute_url = self._normalize_url(href)
            external_id = self._extract_external_id(figure, absolute_url)
            if not external_id or not absolute_url:
                continue

            title = self._text(card.select_one("[data-test-block='ProductName']"))
            if not title and link:
                title = link.get("title")
            price = self._parse_price(self._text(card.select_one("[data-test-block='ProductPrice']")))
            image = card.select_one("image[xlink\\:href], image[href], img[src]")

            listings.append(
                ParsedListing(
                    platform=self.platform,
                    external_id=external_id,
                    title=title,
                    price=price,
                    url=absolute_url,
                    image_url=self._image_url(image),
                )
            )

        return self._deduplicate(listings)

    def _parse_embedded_links(self, soup: BeautifulSoup) -> list[ParsedListing]:
        listings = []
        html = str(soup)
        for raw_url in re.findall(r"(?:https://youla\.ru)?/[a-z0-9_-]+(?:/[a-z0-9_-]+)+-[0-9a-f]{20,32}", html):
            absolute_url = self._normalize_url(raw_url)
            external_id = self._id_from_url(absolute_url)
            if not external_id or not absolute_url:
                continue
            listings.append(
                ParsedListing(
                    platform=self.platform,
                    external_id=external_id,
                    title=None,
                    price=None,
                    url=absolute_url,
                )
            )
        return self._deduplicate(listings)

    def _extract_external_id(self, figure, url: str | None) -> str | None:
        if figure:
            test_id = figure.get("data-test-id")
            if test_id:
                return str(test_id)
        return self._id_from_url(url)

    def _id_from_url(self, url: str | None) -> str | None:
        if not url:
            return None
        slug = urlsplit(url).path.rstrip("/").split("/")[-1]
        match = re.search(r"-([0-9a-f]{20,32})$", slug, re.IGNORECASE)
        return match.group(1) if match else None

    def _normalize_url(self, url: str | None) -> str | None:
        if not url:
            return None
        absolute = urljoin("https://youla.ru", url)
        parts = urlsplit(absolute)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    def _parse_price(self, value) -> int | None:
        if value is None:
            return None
        digits = re.sub(r"\D", "", str(value))
        return int(digits) if digits else None

    def _image_url(self, node) -> str | None:
        if not node:
            return None
        return node.get("src") or node.get("href") or node.get("xlink:href")

    def _log_empty_response(self, url: str, response: requests.Response, soup: BeautifulSoup):
        html = response.text
        lowered = html.lower()
        title = self._text(soup.select_one("title"))
        diagnostics = {
            "status_code": response.status_code,
            "final_url": response.url,
            "html_length": len(html),
            "title": title,
            "product_card_markers": html.count("ProductOrAdCard"),
            "product_name_markers": html.count("ProductName"),
            "product_card_components": html.count("ProductCard"),
            "youla_links": len(re.findall(r"https?://youla\.ru|href=\"/", html)),
            "captcha_markers": any(marker in lowered for marker in ("captcha", "robot", "verify", "access denied")),
            "script_tags": len(soup.select("script")),
            "cookie_names_used": sorted(settings.youla_cookies.keys()),
        }
        logger.warning("Youla parser returned 0 listings for %s. Diagnostics: %s", url, diagnostics)

        if not settings.parser_debug_html:
            return

        settings.parser_debug_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        debug_file = settings.parser_debug_path / f"youla_{timestamp}.html"
        debug_file.write_text(html, encoding=response.encoding or "utf-8")
        logger.warning("Saved Youla debug HTML to %s", debug_file)

    def _text(self, node) -> str | None:
        if not node:
            return None
        text = node.get_text(" ", strip=True)
        return text or None

    def _deduplicate(self, listings: list[ParsedListing]) -> list[ParsedListing]:
        seen = set()
        unique = []
        for listing in listings:
            if listing.external_id in seen:
                continue
            seen.add(listing.external_id)
            unique.append(listing)
        return unique
