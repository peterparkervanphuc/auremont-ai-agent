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


# --- Automatic route --------------------------------------------------------------------


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
    """"phòng" is a filename token, never a question phrase. Reading it as one turns
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


# --- Requested route (regression guards — this behaviour predates the automatic route) ---


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


# --- Failure posture --------------------------------------------------------------------


def test_a_broken_catalogue_never_costs_the_answer():
    """Images are a nice-to-have; collect_images swallows its own failures."""

    class _ExplodingDb:
        def query(self, _model):
            raise RuntimeError("catalogue unavailable")

    assert answer_images_service.collect_images(_ExplodingDb(), "tiện ích The Palma có gì", "") == []


# --- select_listing_images / select_listing_amenities (property listing cards) ----------

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
    listing must get the "can-ho-2pn-..." shots first, not just any floor plan."""
    selected = answer_images_service.select_listing_images(SENIQUE_GALLERY, "2PN")

    assert selected[0] == "https://cdn/p/senique/can-ho-2pn-large-813-m2-the-senique-hanoi.jpg"
    assert selected[1] == "https://cdn/p/senique/can-ho-2pn-medium-643-m2-the-senique-hanoi.jpg"
    # 1PN/3PN photos are the wrong unit type — they must not crowd out the overview shot.
    assert "https://cdn/p/senique/phoi-canh-tong-the-the-senique-hanoi.jpg" in selected


def test_select_listing_images_prefers_any_floor_plan_over_the_overview_shot():
    """The Pavilion tags floor plans by tower, not by unit type — with no exact "2PN" tag
    to match, a listing still prefers whatever floor-plan photos the subdivision does have
    (still "mặt bằng" content) ahead of the generic overview shot."""
    selected = answer_images_service.select_listing_images(PAVILION_GALLERY, "2PN")

    assert selected[0] == "https://cdn/p/the-pavilion/mat-bang-toa-p1.jpg"
    assert "https://cdn/p/the-pavilion/tong-mat-bang-the-pavilion.jpg" in selected


def test_select_listing_images_falls_back_to_subdivision_overview_shots_with_no_floor_plans():
    """When a subdivision's gallery has no floor-plan photo at all, a listing still gets
    the overview shot rather than an unrelated amenity photo."""
    gallery = [
        "https://cdn/p/the-palma/tien-ich-be-boi.jpg",
        "https://cdn/p/the-palma/tien-ich-gym.jpg",
        "https://cdn/p/the-palma/phoi-canh-tong-the.jpg",
    ]

    selected = answer_images_service.select_listing_images(gallery, "2PN")

    assert selected[0] == "https://cdn/p/the-palma/phoi-canh-tong-the.jpg"


def test_select_listing_images_caps_at_five():
    gallery = [f"https://cdn/p/x/photo-{i}.jpg" for i in range(12)]

    assert len(answer_images_service.select_listing_images(gallery, "2PN")) == 5


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
