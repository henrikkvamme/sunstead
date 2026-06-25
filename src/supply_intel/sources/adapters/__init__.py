from supply_intel.models.source import SourceConfig
from supply_intel.sources.adapters.base import SourceAdapter
from supply_intel.sources.adapters.document import PdfDocumentAdapter
from supply_intel.sources.adapters.file_download import FileDownloadAdapter
from supply_intel.sources.adapters.manual import ManualSeedAdapter
from supply_intel.sources.adapters.rest import (
    HtmlScraperAdapter,
    PaginatedRestAdapter,
    RssAtomAdapter,
)


def adapter_for_source(config: SourceConfig) -> SourceAdapter:
    if config.adapter in {"rest", "paginated_rest"}:
        return PaginatedRestAdapter()
    if config.adapter == "html_scraper":
        return HtmlScraperAdapter()
    if config.adapter == "rss":
        return RssAtomAdapter()
    if config.adapter == "manual_seed":
        return ManualSeedAdapter()
    if config.adapter == "file_download":
        return FileDownloadAdapter()
    if config.adapter == "pdf_document":
        return PdfDocumentAdapter()
    raise ValueError(f"Adapter runtime is not implemented for {config.adapter}")
