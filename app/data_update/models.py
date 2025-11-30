from datetime import datetime

from pydantic import BaseModel, field_validator
from wikidot.module.page import Page


class PageInfo(BaseModel):
    fullname: str
    title: str
    created_at: datetime
    created_by_unix: str | None
    created_by_id: int | None
    created_by: str | None
    updated_at: datetime | None
    updated_by: str | None
    updated_by_unix: str | None
    updated_by_id: int | None
    commented_at: datetime | None
    commented_by: str | None
    commented_by_unix: str | None
    commented_by_id: int | None
    parent_fullname: str | None
    comments: int
    size: int
    rating: int | float
    rating_votes: int
    revisions: int
    tags: list[str]

    @staticmethod
    def from_wikidot_py(page: Page) -> "PageInfo":
        return PageInfo(
            fullname=page.fullname,
            title=page.title,
            created_at=page.created_at,
            created_by_unix=page.created_by.unix_name,
            created_by_id=page.created_by.id,
            created_by=page.created_by.name,
            updated_at=page.updated_at,
            updated_by=page.updated_by.name,
            updated_by_unix=page.updated_by.unix_name,
            updated_by_id=page.updated_by.id,
            commented_at=page.commented_at,
            commented_by=page.commented_by.name if page.commented_by else None,
            commented_by_unix=page.commented_by.unix_name
            if page.commented_by
            else None,
            commented_by_id=page.commented_by.id if page.commented_by else None,
            parent_fullname=page.parent_fullname,
            comments=page.comments_count,
            size=page.size,
            rating=page.rating,
            rating_votes=page.votes_count,
            revisions=page.revisions_count,
            tags=page.tags,
        )


# Crom API response models


class CromAlternateTitle(BaseModel):
    title: str


class CromUser(BaseModel):
    name: str


class CromAttribution(BaseModel):
    type: str
    user: CromUser


class CromCoarseVoteRecord(BaseModel):
    timestamp: datetime
    direction: int | float


class CromWikidotInfo(BaseModel):
    title: str
    tags: list[str]
    rating: int | float
    coarseVoteRecords: list[CromCoarseVoteRecord]


class CromPage(BaseModel):
    url: str
    alternateTitles: list[CromAlternateTitle]
    attributions: list[CromAttribution]
    wikidotInfo: CromWikidotInfo


class AyameDatePage(BaseModel):
    fullname: str
    title: str
    created_at: datetime
    created_by_unix: str | None
    created_by_id: int | None
    created_by: str | None
    updated_at: datetime | None
    updated_by: str | None
    updated_by_unix: str | None
    updated_by_id: int | None
    commented_at: datetime | None
    commented_by: str | None
    commented_by_unix: str | None
    commented_by_id: int | None
    parent_fullname: str | None
    comments: int
    size: int
    rating: int | float
    revisions: int
    tags: list[str]
    metatitle: str | None
    id: int
    date: str

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate that date is in YYYY-MM-DD format."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("date must be in YYYY-MM-DD format")
        return v

    @staticmethod
    def create_date_page(
        page_data: PageInfo,
        metatitle: str | None,
        article_id: int,
        date: str,
        rating: int | float,
    ) -> "AyameDatePage":
        return AyameDatePage(
            fullname=page_data.fullname,
            title=page_data.title,
            created_at=page_data.created_at,
            created_by_unix=page_data.created_by_unix,
            created_by_id=page_data.created_by_id,
            created_by=page_data.created_by,
            updated_at=page_data.updated_at,
            updated_by=page_data.updated_by,
            updated_by_unix=page_data.updated_by_unix,
            updated_by_id=page_data.updated_by_id,
            commented_at=page_data.commented_at,
            commented_by=page_data.commented_by,
            commented_by_unix=page_data.commented_by_unix,
            commented_by_id=page_data.commented_by_id,
            parent_fullname=page_data.parent_fullname,
            comments=page_data.comments,
            size=page_data.size,
            rating=rating,
            rating_votes=page_data.rating_votes,
            revisions=page_data.revisions,
            tags=page_data.tags,
            metatitle=metatitle,
            id=article_id,
            date=date,
        )
