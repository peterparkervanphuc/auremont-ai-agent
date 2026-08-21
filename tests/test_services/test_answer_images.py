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


def _urls(images: list[dict]) -> list[str]:
    return [image["url"] for image in images]


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
