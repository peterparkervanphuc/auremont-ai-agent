"""The two routes photos reach an answer by — see answer_images_service's module docstring.

Requested: the question asked to see something, gets everything matching, uncapped, and
falls back to the whole gallery rather than returning nothing.

Automatic: the question only asked to know something, and photos ride along to illustrate
the text. Capped, and NO fallback — an unasked-for photo of the wrong thing is worse than
no photo at all.
"""

from backend.services import answer_images_service
from backend.services.answer_images_service import _AUTO_ATTACH_MAX_IMAGES

GALLERY = [
    "https://cdn/p/the-palma/tien-ich-be-boi.jpg",
    "https://cdn/p/the-palma/tien-ich-cong-vien.jpg",
    "https://cdn/p/the-palma/tien-ich-gym.jpg",
    "https://cdn/p/the-palma/tien-ich-san-tennis.jpg",
    "https://cdn/p/the-palma/mat-bang-tang-5.jpg",
    "https://cdn/p/the-palma/phoi-canh-tong-the.jpg",
]

GALLERY_PHONG_NAMES = [
    "https://cdn/p/the-london/phong-dance-phan-khu-the-london-vinhomes-ocean-park.jpg",
    "https://cdn/p/the-london/phong-tap-gym-phan-khu-the-london-vinhomes-ocean-park.jpg",
    "https://cdn/p/the-london/phong-karaoke-phan-khu-the-london-vinhomes-ocean-park.jpg",
    "https://cdn/p/the-london/phoi-canh-tong-the-the-london.jpg",
]

PAVILION_GALLERY = [
    "https://cdn/p/the-pavilion/mat-bang-toa-p1.jpg",
    "https://cdn/p/the-pavilion/mat-bang-toa-p2.jpg",
    "https://cdn/p/the-pavilion/mat-bang-toa-p3.jpg",
    "https://cdn/p/the-pavilion/mat-bang-toa-p4.jpg",
    "https://cdn/p/the-pavilion/tong-mat-bang-the-pavilion.jpg",
]


class _FakeProject:
    id = "the-palma"
    name = "The Palma"
    details = {"images": {"gallery": GALLERY}}


class _FakeLondonProject:
    """A real-catalogue naming convention: amenity photos are named after the specific
    room ("phong-tap-gym-..."), never with the generic word "tiện ích"."""

    id = "the-london"
    name = "The London"
    details = {"images": {"gallery": GALLERY_PHONG_NAMES}}


class _FakePavilionProject:
    id = "the-pavilion"
    name = "The Pavilion"
    details = {"images": {"gallery": PAVILION_GALLERY}}


class _FakeSapphireProject:
    id = "the-sapphire"
    name = "The Sapphire - Vinhomes Ocean Park"
    details = {"images": {"gallery": []}}


class _ConfiguredAliasProject:
    id = "catalogue-project-a"
    name = "Catalogue Project A"
    details = {
        "project": {"aliases": ["Customer Alias One"]},
        "images": {"gallery": []},
    }


class _FakeQuery:
    def __init__(self, projects):
        self._projects = projects

    def all(self):
        return self._projects


class _FakeDb:
    def __init__(self, *projects):
        self._projects = list(projects) or [_FakeProject()]

    def query(self, _model):
        return _FakeQuery(self._projects)

    def get(self, _model, project_id):
        return next((project for project in self._projects if project.id == project_id), None)


def _urls(images: list[dict]) -> list[str]:
    return [image["url"] for image in images]


def test_resolve_project_ids_keeps_both_sides_of_a_comparison():
    projects = answer_images_service.resolve_project_ids(
        _FakeDb(_FakePavilionProject(), _FakeProject()),
        "So sánh The Pavilion và The Palma",
    )

    assert projects == ["the-pavilion", "the-palma"]


def test_resolve_project_ids_accepts_names_without_the_prefix():
    projects = answer_images_service.resolve_project_ids(
        _FakeDb(_FakeSapphireProject(), _FakePavilionProject()),
        "Khách đang so sánh Sapphire 2 và Pavilion",
    )

    assert projects == ["the-sapphire", "the-pavilion"]


def test_project_aliases_come_from_catalogue_metadata():
    projects = answer_images_service.resolve_project_ids(
        _FakeDb(_ConfiguredAliasProject()),
        "Cho tôi thông tin Customer Alias One",
    )

    assert projects == ["catalogue-project-a"]


def test_negative_project_mention_never_selects_its_gallery():
    db = _FakeDb(_FakeProject(), _FakePavilionProject())

    images = answer_images_service.collect_images(
        db,
        "Ngoài The Palma thì còn phân khu nào khác?",
        "Có thể cân nhắc The Pavilion.",
    )

    assert images == []


def test_amenity_question_attaches_amenity_photos_without_being_asked():
    """The headline case: asking what the amenities ARE now shows them too."""
    images = answer_images_service.collect_images(_FakeDb(), "tiện ích dự án The Palma có gì", "")

    assert images, "an amenity question should carry amenity photos"
    assert all("tien-ich" in url for url in _urls(images))


def test_automatic_attachment_is_capped():
    """Four amenity photos exist; an unrequested strip must not run to all of them."""
    images = answer_images_service.collect_images(_FakeDb(), "tiện ích dự án The Palma có gì", "")

    assert len(images) == _AUTO_ATTACH_MAX_IMAGES


def test_amenity_question_matches_room_named_photos():
    """Regression for a real miss: The London's amenity photos are named per room
    ("phong-tap-gym-...", "phong-karaoke-...") with no "tien-ich" anywhere in the
    filename, so an amenity question found nothing and fell through to the project's
    establishing shot — a site map shown under a list of gyms and karaoke rooms."""
    db = _FakeDb(_FakeLondonProject())
    images = answer_images_service.collect_images(db, "The London có những tiện ích gì", "")

    assert images, "room-named amenity photos must match an amenity question"
    assert all("phong-" in url for url in _urls(images))
    assert not any("phoi-canh" in url for url in _urls(images))


def test_bedroom_count_is_not_read_as_an_amenity_question():
    """ "phòng" is a filename token, never a question phrase. Reading it as one turns
    "giá căn 2 phòng ngủ" into an amenity question and hangs gym and pool photos off a
    price answer."""
    db = _FakeDb(_FakeLondonProject())
    images = answer_images_service.collect_images(db, "giá căn 2 phòng ngủ The London", "")

    assert not any("phong-" in url for url in _urls(images))


def test_automatic_attachment_does_not_fall_back_to_unrelated_photos():
    """No interior photos in this gallery — the answer goes out with none rather than
    with whatever else was lying around, unlike the requested route below."""
    images = answer_images_service.collect_images(_FakeDb(), "nội thất bàn giao The Palma thế nào", "")

    assert images == []


def test_question_with_no_visual_topic_gets_overview_photos():
    """A price question names nothing photographable, so it gets the establishing shots —
    never the amenity or floor-plan photos, which would claim to depict something the
    asker never mentioned."""
    images = answer_images_service.collect_images(_FakeDb(), "giá căn 2 phòng ngủ The Palma bao nhiêu", "")

    assert _urls(images) == ["https://cdn/p/the-palma/phoi-canh-tong-the.jpg"]


def test_lake_view_question_does_not_match_apartment_or_unlabelled_landscape_photos():
    """Accent stripping makes the Vietnamese words for lake and apartment end in
    ``ho``. A view question must not attach every ``can-ho-*`` layout, or a landscape
    photo that does not prove it is the view from a unit."""

    class _ViewProject:
        id = "catalogue-project-a"
        name = "The Palma"
        details = {
            "images": {
                "gallery": [
                    "https://cdn/p/the-palma/can-ho-2-ngu.jpg",
                    "https://cdn/p/the-palma/canh-quan-noi-khu.jpg",
                    "https://cdn/p/the-palma/view-thanh-pho.jpg",
                ]
            }
        }

    images = answer_images_service.collect_images(
        _FakeDb(_ViewProject()),
        "The Palma co loai view nao? Can nao view ho hoac canh quan noi khu?",
        "",
    )

    assert images == []


def test_generic_view_question_only_attaches_explicitly_labelled_view_photos():
    class _ViewProject:
        id = "catalogue-project-a"
        name = "The Palma"
        details = {
            "images": {
                "gallery": [
                    "https://cdn/p/the-palma/can-ho-2-ngu.jpg",
                    "https://cdn/p/the-palma/view-tu-can-ho.jpg",
                ]
            }
        }

    images = answer_images_service.collect_images(_FakeDb(_ViewProject()), "The Palma co view the nao?", "")

    assert _urls(images) == ["https://cdn/p/the-palma/view-tu-can-ho.jpg"]


def test_project_named_only_in_the_answer_still_attaches():
    """A follow-up rarely repeats the project name; retrieval's answer carries it."""
    images = answer_images_service.collect_images(_FakeDb(), "tiện ích có gì", "Dự án The Palma có bể bơi...")

    assert images
    assert all("tien-ich" in url for url in _urls(images))


def test_exact_tower_question_attaches_the_named_tower_instead_of_first_three():
    db = _FakeDb(_FakePavilionProject())

    images = answer_images_service.collect_images(
        db,
        "Cho tôi biết thông tin tòa P4. Tòa này thuộc phân khu nào?",
        "Tòa P4 thuộc The Pavilion.",
    )

    assert _urls(images) == ["https://cdn/p/the-pavilion/mat-bang-toa-p4.jpg"]


def test_session_project_scope_wins_over_a_longer_parent_project_name():
    class _ParentProject:
        id = "vinhomes-ocean-park"
        name = "Vinhomes Ocean Park"
        details = {"images": {"gallery": ["https://cdn/parent/mat-bang-toa-p4.jpg"]}}

    db = _FakeDb(_ParentProject(), _FakePavilionProject())

    images = answer_images_service.collect_images(
        db,
        "Cho tôi thông tin tòa P4",
        "P4 thuộc The Pavilion tại Vinhomes Ocean Park",
        project_id="the-pavilion",
    )

    assert _urls(images) == ["https://cdn/p/the-pavilion/mat-bang-toa-p4.jpg"]


def test_dotted_tower_code_matches_hyphenated_catalogue_filename():
    class _SapphireProject:
        id = "the-sapphire"
        name = "The Sapphire"
        details = {
            "project": {"overview": {"towers": ["S1.02", "S1.03"]}},
            "images": {
                "gallery": [
                    "https://cdn/sapphire/mat-bang-toa-S1-02.jpg",
                    "https://cdn/sapphire/mat-bang-toa-S1-03.jpg",
                ]
            },
        }

    images = answer_images_service.collect_images(
        _FakeDb(_SapphireProject()),
        "Cho tôi thông tin tòa S1.02",
        "Tòa S1.02 thuộc The Sapphire",
        project_id="the-sapphire",
    )

    assert _urls(images) == ["https://cdn/sapphire/mat-bang-toa-S1-02.jpg"]


def test_named_tower_without_an_uploaded_plan_does_not_show_another_tower():
    class _PartialProject:
        id = "the-beverly"
        name = "The Beverly"
        details = {
            "project": {"overview": {"towers": ["BE1", "BE2"]}},
            "images": {"gallery": ["https://cdn/beverly/mat-bang-toa-be1.jpg"]},
        }

    images = answer_images_service.collect_images(
        _FakeDb(_PartialProject()),
        "Cho tôi thông tin tòa BE2",
        "Tòa BE2 thuộc The Beverly",
        project_id="the-beverly",
    )

    assert images == []


def test_unknown_project_attaches_nothing():
    images = answer_images_service.collect_images(_FakeDb(), "tiện ích Vinhomes Smart City có gì", "")

    assert images == []


def test_requested_photos_are_not_capped():
    """Someone who explicitly asked to see the amenities gets all four, not the automatic
    route's three."""
    images = answer_images_service.collect_images(_FakeDb(), "cho xem hình ảnh tiện ích The Palma", "")

    assert len(images) == 4
    assert all("tien-ich" in url for url in _urls(images))


def test_requested_photos_fall_back_to_the_whole_gallery():
    """Refusing someone who explicitly asked to see something is the worse failure, so an
    unmatched topic still returns the project's photos."""
    images = answer_images_service.collect_images(_FakeDb(), "cho xem hình ảnh nội thất The Palma", "")

    assert _urls(images) == GALLERY


def test_floor_plan_request_still_narrows_to_floor_plans():
    images = answer_images_service.collect_images(_FakeDb(), "cho xem mặt bằng The Palma", "")

    assert _urls(images) == ["https://cdn/p/the-palma/mat-bang-tang-5.jpg"]


def test_a_broken_catalogue_never_costs_the_answer():
    """Images are a nice-to-have; collect_images swallows its own failures."""

    class _ExplodingDb:
        def query(self, _model):
            raise RuntimeError("catalogue unavailable")

    assert answer_images_service.collect_images(_ExplodingDb(), "tiện ích The Palma có gì", "") == []


SENIQUE_GALLERY = [
    "https://cdn/p/senique/be-boi-50m-the-senique-hanoi.jpg",
    "https://cdn/p/senique/can-ho-1pn-medium-42-m2-the-senique-hanoi.jpg",
    "https://cdn/p/senique/can-ho-2pn-large-813-m2-the-senique-hanoi.jpg",
    "https://cdn/p/senique/can-ho-2pn-medium-643-m2-the-senique-hanoi.jpg",
    "https://cdn/p/senique/can-ho-3pn-small-832-m2-the-senique-hanoi.jpg",
    "https://cdn/p/senique/phoi-canh-tong-the-the-senique-hanoi.jpg",
    "https://cdn/p/senique/vi-tri-the-senique-hanoi.jpg",
]


def test_select_listing_images_prefers_unit_type_tagged_floor_plans():
    """The Senique Hanoi tags floor plans by bedroom count in the filename — a "2PN"
    listing must get exactly the "can-ho-2pn-..." shots, not the 1PN/3PN photos and not
    the overview shot: once a unit type has its own real photos, nothing else is padded
    in alongside them (that padding is exactly what showed the wrong photo in practice —
    see the module docstring on select_listing_images)."""
    selected = answer_images_service.select_listing_images(SENIQUE_GALLERY, "2PN")

    assert selected == [
        "https://cdn/p/senique/can-ho-2pn-large-813-m2-the-senique-hanoi.jpg",
        "https://cdn/p/senique/can-ho-2pn-medium-643-m2-the-senique-hanoi.jpg",
    ]


def test_select_listing_images_returns_nothing_when_only_tower_wide_plans_exist():
    """The Pavilion's gallery only tags floor plans by tower ("mat-bang-toa-p1"), never by
    unit type, and has no true overview shot ("tong-mat-bang" is not "tong-the"/"phoi-canh"/
    "toan-canh"). A tower-wide floor plan is not an accurate photo of "2PN" specifically —
    showing one anyway (the old behaviour) was the exact complaint that led to this
    function's rewrite, so the correct result here is no photo at all rather than a wrong
    one."""
    selected = answer_images_service.select_listing_images(PAVILION_GALLERY, "2PN")

    assert selected == []


def test_select_listing_images_falls_back_to_every_other_real_photo_with_no_floor_plans():
    """When a subdivision's gallery has no unit-type-tagged photo at all, a listing gets
    every other real photo of the project (amenities, overview shots — anything that is
    not a floor plan), not just whichever happens to carry the narrow "phoi-canh"/
    "tong-the" overview keywords. The Palma has several genuine scenic photos that don't
    carry those exact keywords; stopping at the narrow overview-only set under-showed
    real photos of the right project for no good reason."""
    gallery = [
        "https://cdn/p/the-palma/tien-ich-be-boi.jpg",
        "https://cdn/p/the-palma/tien-ich-gym.jpg",
        "https://cdn/p/the-palma/phoi-canh-tong-the.jpg",
        "https://cdn/p/the-palma/mat-bang-toa-1.jpg",
    ]

    selected = answer_images_service.select_listing_images(gallery, "2PN")

    assert selected == [
        "https://cdn/p/the-palma/tien-ich-be-boi.jpg",
        "https://cdn/p/the-palma/tien-ich-gym.jpg",
        "https://cdn/p/the-palma/phoi-canh-tong-the.jpg",
    ]


def test_select_listing_images_has_no_fixed_cap():
    """Accuracy matters more than a fixed photo count — every genuine match for the unit
    type is returned, not trimmed down to some arbitrary number."""
    gallery = [f"https://cdn/p/x/can-ho-2pn-{i}.jpg" for i in range(12)]

    assert len(answer_images_service.select_listing_images(gallery, "2PN")) == 12


def test_select_listing_images_empty_gallery_returns_empty():
    assert answer_images_service.select_listing_images([], "2PN") == []


class _FakeProjectWithAmenities:
    details = {
        "amenities": [
            {"name": "Sân chơi trẻ em", "zone": "Sapphire 1"},
            {"name": "Vườn dưỡng sinh", "zone": "Sapphire 1"},
            {"name": "Hồ bơi", "zone": "Sapphire 1"},
            {"name": "Sân tennis", "zone": "Sapphire 1"},
            {"name": "Phòng gym", "zone": "Sapphire 1"},
        ]
    }


def test_select_listing_amenities_returns_a_few_names():
    names = answer_images_service.select_listing_amenities(_FakeProjectWithAmenities())

    assert names == ["Sân chơi trẻ em", "Vườn dưỡng sinh", "Hồ bơi", "Sân tennis"]


class _FakeProjectWithoutAmenities:
    details: dict = {}


def test_select_listing_amenities_handles_missing_data():
    assert answer_images_service.select_listing_amenities(_FakeProjectWithoutAmenities()) == []


ZENPARK_FOLDERED_GALLERY = [
    "https://cdn/p/the-zenpark/tien_ich/be-boi-4-mua-the-zenpark.jpg",
    "https://cdn/p/the-zenpark/tien_ich/san-the-thao-the-zenpark.jpg",
    "https://cdn/p/the-zenpark/tien_ich/vuon-nhat-the-zenpark.jpg",
    "https://cdn/p/the-zenpark/mat_bang/toa-r1-02-zenpark.jpg",
    "https://cdn/p/the-zenpark/hinh_anh_thuc_te/cau-nhat-the-zenpark.jpg",
]


def test_amenity_question_matches_photos_labelled_only_by_their_folder():
    picked = answer_images_service._auto_attach_images(ZENPARK_FOLDERED_GALLERY, "tien ich the zenpark", [])

    assert sorted(url.rsplit("/", 1)[-1] for url in picked) == [
        "be-boi-4-mua-the-zenpark.jpg",
        "san-the-thao-the-zenpark.jpg",
        "vuon-nhat-the-zenpark.jpg",
    ]


def test_floor_plan_question_does_not_pull_in_the_amenity_folder():
    picked = answer_images_service._auto_attach_images(ZENPARK_FOLDERED_GALLERY, "mat bang the zenpark", [])

    assert [url.rsplit("/", 1)[-1] for url in picked] == ["toa-r1-02-zenpark.jpg"]


def test_project_slug_before_the_filename_is_never_read_as_a_folder():
    """Four catalogues are named `shop-thuong-mai-*`, and gallery entries are full URLs.

    Were the segment before the filename taken as a category unconditionally, every photo
    in those catalogues would answer to "shop"/"thuong mai" regardless of what it depicts.
    """
    gallery = [
        "https://cdn/p/shop-thuong-mai-sh09/noi-that-sh09.jpg",
        "https://cdn/p/shop-thuong-mai-sh09/shop-tmdv-sh09.jpg",
    ]

    picked = answer_images_service._auto_attach_images(gallery, "cho xem shop", [])

    assert [url.rsplit("/", 1)[-1] for url in picked] == ["shop-tmdv-sh09.jpg"]
