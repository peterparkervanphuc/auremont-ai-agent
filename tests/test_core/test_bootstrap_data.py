from types import SimpleNamespace

from backend.core import bootstrap_data


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Session:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _model):
        return _Query(self.rows)

    def close(self):
        pass


def test_one_populated_project_is_not_mistaken_for_a_complete_catalogue(monkeypatch):
    rows = [SimpleNamespace(id="parent", details={"project": {"id": "parent"}})]
    monkeypatch.setattr(bootstrap_data, "SessionLocal", lambda: _Session(rows))
    monkeypatch.setattr(bootstrap_data, "_expected_catalogue_ids", lambda: {"parent", "child"})

    assert bootstrap_data._catalogue_is_loaded() is False


def test_catalogue_is_complete_only_when_every_seed_record_is_present(monkeypatch):
    rows = [
        SimpleNamespace(id="parent", details={"project": {"id": "parent"}}),
        SimpleNamespace(id="child", details={"project": {"id": "child"}}),
    ]
    monkeypatch.setattr(bootstrap_data, "SessionLocal", lambda: _Session(rows))
    monkeypatch.setattr(bootstrap_data, "_expected_catalogue_ids", lambda: {"parent", "child"})

    assert bootstrap_data._catalogue_is_loaded() is True


def test_existing_catalogue_still_syncs_missing_project_images(monkeypatch):
    settings = SimpleNamespace(
        auto_load_demo_data=True,
        project_images_archive_url="https://cdn.example.test/project-images.tar.gz",
        project_images_base_url="https://cdn.example.test/project-images",
    )
    downloaded: list[str] = []
    monkeypatch.setattr(bootstrap_data, "get_settings", lambda: settings)
    monkeypatch.setattr(bootstrap_data, "_catalogue_is_loaded", lambda: True)
    monkeypatch.setattr(
        bootstrap_data,
        "_download_archive_to_minio",
        lambda url: downloaded.append(url) or 2,
    )

    bootstrap_data.load_demo_data()

    assert downloaded == [settings.project_images_archive_url]
