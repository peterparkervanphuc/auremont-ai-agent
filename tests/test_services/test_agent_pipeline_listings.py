"""Property listing cards: numeric details (loại căn/diện tích/giá) moved out of the
answer's prose text into their own structured field so the frontend can render them as
paged cards instead of bullet lines — see prompts.PropertyListing and
CustomerChatPage.tsx's PropertyListingCarousel.

The regression this file guards against: `_risk_check` decides `requires_hitl` by
regex-scanning `draft_answer` (risk_service.detect_commitment_risk). Moving price/area out
of that text and into `listings` would make a price-bearing recommendation invisible to
that scan unless `_risk_check` is taught to look at `listings` too — exactly the class of
answer RiskCheck exists to catch, so a miss here is the worst possible one.
"""

from backend.ai.prompts import PropertyListing
from backend.models.project import Project
from backend.services import agent_pipeline


class _FakeDb:
    """Just enough of a Session for `_resolve_listing_images`, which only ever calls
    `db.get(Project, project_id)` — no real database needed for this."""

    def __init__(self, projects: dict[str, Project]):
        self._projects = projects

    def get(self, _model: type, pk: str | None) -> Project | None:
        return self._projects.get(pk) if pk else None


def _listing(**overrides: str) -> PropertyListing:
    defaults = {
        "project_name": "The Sapphire 2",
        "unit_type": "2PN",
        "area_range": "55-64 m²",
        "price_range": "3,1-4,3 tỷ đồng",
    }
    return PropertyListing(**{**defaults, **overrides})


def test_risk_check_catches_a_price_that_only_lives_in_listings():
    """draft_answer itself is deliberately price-free — only `listings` carries a figure —
    to prove the scan actually reads listings, not just draft_answer."""
    state = {
        "draft_answer": "Với ngân sách này, em gợi ý lựa chọn sau ạ:",
        "listings": [
            {
                "project_name": "The Sapphire 2",
                "unit_type": "2PN",
                "area_range": "55-64 m²",
                "price_range": "3,1-4,3 tỷ đồng",
                "image_urls": [],
                "amenities": [],
                "project_id": None,
            }
        ],
    }

    result = agent_pipeline._risk_check(state)

    assert result["requires_hitl"] is True


def test_risk_check_stays_false_with_no_listings_and_a_price_free_answer():
    result = agent_pipeline._risk_check({"draft_answer": "Dự án nằm ở Gia Lâm, Hà Nội.", "listings": []})

    assert result["requires_hitl"] is False


def test_resolve_listing_images_attaches_real_gallery_photos_and_amenities(monkeypatch):
    monkeypatch.setattr(agent_pipeline.answer_images_service, "resolve_project_id", lambda _db, text: "the-sapphire-2")
    db = _FakeDb(
        {
            "the-sapphire-2": Project(
                id="the-sapphire-2",
                name="The Sapphire 2",
                details={
                    # Filenames must actually tag the "2PN" unit type — select_listing_images
                    # no longer falls back to attaching just any gallery photo (see
                    # test_answer_images.py for the dedicated coverage of that behaviour).
                    "images": {
                        "gallery": [
                            "http://minio/sapphire-2/can-ho-2pn-a.jpg",
                            "http://minio/sapphire-2/can-ho-2pn-b.jpg",
                        ]
                    },
                    "amenities": [{"name": "Hồ bơi"}, {"name": "Sân tennis"}],
                },
            )
        }
    )

    resolved = agent_pipeline._resolve_listing_images(db, [_listing()])

    assert resolved == [
        {
            "project_name": "The Sapphire 2",
            "unit_type": "2PN",
            "area_range": "55-64 m²",
            "price_range": "3,1-4,3 tỷ đồng",
            "image_urls": ["http://minio/sapphire-2/can-ho-2pn-a.jpg", "http://minio/sapphire-2/can-ho-2pn-b.jpg"],
            "amenities": ["Hồ bơi", "Sân tennis"],
            "project_id": "the-sapphire-2",
            # Catalogue-only card: no live inventory record behind it, so both stay "".
            "unit_code": "",
            "status": "",
        }
    ]


def test_resolve_listing_images_keeps_the_listing_when_nothing_resolves(monkeypatch):
    monkeypatch.setattr(agent_pipeline.answer_images_service, "resolve_project_id", lambda _db, text: None)

    resolved = agent_pipeline._resolve_listing_images(_FakeDb({}), [_listing()])

    assert resolved == [
        {
            "project_name": "The Sapphire 2",
            "unit_type": "2PN",
            "area_range": "55-64 m²",
            "price_range": "3,1-4,3 tỷ đồng",
            "image_urls": [],
            "amenities": [],
            "project_id": None,
            "unit_code": "",
            "status": "",
        }
    ]


def test_resolve_listing_images_handles_a_missing_db():
    resolved = agent_pipeline._resolve_listing_images(None, [_listing()])

    assert resolved[0]["image_urls"] == []
    assert resolved[0]["amenities"] == []
    assert resolved[0]["project_id"] is None
    assert resolved[0]["project_name"] == "The Sapphire 2"
