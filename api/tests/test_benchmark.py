"""The AI benchmark screen's data: only office roles see it, and the photo route cannot be used to read other files."""
from httpx import AsyncClient

from tests.test_upload_links import biller


async def test_runs_and_photos_need_an_office_login(client: AsyncClient) -> None:
    assert (await client.get("/benchmark/runs")).status_code == 401
    assert (await client.get("/benchmark/photos/S01_flat.jpeg")).status_code == 401


async def test_the_runs_list_comes_back_for_an_office_user(client: AsyncClient) -> None:
    res = await client.get("/benchmark/runs", headers=await biller(client))
    assert res.status_code == 200 and isinstance(res.json(), list)
    for run in res.json():
        assert {"id", "label", "cases"} <= run.keys()


async def test_a_photo_name_cannot_reach_other_files(client: AsyncClient) -> None:
    h = await biller(client)
    for bad in ("..%2F..%2F.env", "S01.png%00", "notes.jpeg", "S1.jpeg"):
        assert (await client.get(f"/benchmark/photos/{bad}", headers=h)).status_code in (404, 422)
    assert (await client.get("/benchmark/photos/S99.jpeg", headers=h)).status_code == 404
