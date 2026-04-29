from parsers.avito import AvitoParser
from parsers.base import BaseParser
from parsers.cian import CianParser


class ParserFactory:
    def __init__(self):
        self._parsers: dict[str, BaseParser] = {
            AvitoParser.platform: AvitoParser(),
            CianParser.platform: CianParser(),
        }

    @property
    def supported_platforms(self) -> set[str]:
        return set(self._parsers)

    def get(self, platform: str) -> BaseParser:
        try:
            return self._parsers[platform]
        except KeyError as exc:
            supported = ", ".join(sorted(self._parsers))
            raise ValueError(f"Unsupported platform '{platform}'. Supported: {supported}") from exc
