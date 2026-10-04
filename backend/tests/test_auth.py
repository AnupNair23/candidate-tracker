import base64
from contextlib import asynccontextmanager

import httpx
from asgi_lifespan import LifespanManager

from app.main import create_app
from tests.conftest import make_settings


@asynccontextmanager
async def serve(tmp_path, **overrides):
    """A fresh app built from explicit settings (`_env_file=None`), so the real .env is never read."""
    app = create_app(make_settings(tmp_path, **overrides))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


def basic(user: str, password: str) -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


AUTH = dict(basic_auth_user="demo", basic_auth_password="s3cret")


async def test_missing_credentials_get_a_basic_challenge(tmp_path):
    async with serve(tmp_path, **AUTH) as http:
        resp = await http.get("/api/health")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == 'Basic realm="Candidate Tracker"'


async def test_wrong_credentials_are_rejected(tmp_path):
    async with serve(tmp_path, **AUTH) as http:
        wrong_password = await http.get("/api/health", headers=basic("demo", "nope"))
        wrong_user = await http.get("/api/health", headers=basic("admin", "s3cret"))
        garbage = await http.get("/api/health", headers={"Authorization": "Basic !!!not-base64"})
    assert wrong_password.status_code == wrong_user.status_code == garbage.status_code == 401


async def test_correct_credentials_pass(tmp_path):
    async with serve(tmp_path, **AUTH) as http:
        resp = await http.get("/api/health", headers=basic("demo", "s3cret"))
    assert resp.status_code == 200 and resp.json()["ok"] is True


async def test_healthz_is_open_and_reveals_nothing(tmp_path):
    async with serve(tmp_path, **AUTH) as http:
        resp = await http.get("/healthz")
        post = await http.post("/healthz")
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert post.status_code == 401


async def test_auth_unset_leaves_everything_open(tmp_path):
    async with serve(tmp_path) as http:
        health = await http.get("/api/health")
        healthz = await http.get("/healthz")
    assert health.status_code == 200 and healthz.status_code == 200


async def test_spa_fallback_behind_auth(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    async with serve(tmp_path, frontend_dist=dist, **AUTH) as http:
        assert (await http.get("/jobs/21000?tab=sourcing")).status_code == 401
        page = await http.get("/jobs/21000?tab=sourcing", headers=basic("demo", "s3cret"))
        asset = await http.get("/assets/app.js", headers=basic("demo", "s3cret"))
        api_miss = await http.get("/api/nope", headers=basic("demo", "s3cret"))
        escape = await http.get("/..%2F..%2Fetc%2Fpasswd", headers=basic("demo", "s3cret"))
    assert page.status_code == 200 and "<div id=root>" in page.text
    assert asset.text == "console.log(1)"
    assert api_miss.status_code == 404
    assert escape.status_code == 200 and "<div id=root>" in escape.text
