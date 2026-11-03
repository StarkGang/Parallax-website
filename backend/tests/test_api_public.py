"""Tests for public API endpoints: health, config, catalogue and schedule."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoints(client: AsyncClient):
    live = await client.get("/health/live")
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}

    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_public_config(client: AsyncClient):
    resp = await client.get("/api/v1/public/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["environment"] == "test"
    assert data["editionSlug"] == "parallax-2026"


@pytest.mark.asyncio
async def test_current_edition_and_catalogue(client: AsyncClient):
    # Current edition
    resp = await client.get("/api/v1/public/editions/current")
    assert resp.status_code == 200
    edition = resp.json()["data"]
    assert edition["slug"] == "parallax-2026"
    assert edition["name"] == "Parallax 2026"
    assert edition["policy"]["passPricePaise"] == 35000

    # Categories
    cat_resp = await client.get("/api/v1/public/editions/parallax-2026/categories")
    assert cat_resp.status_code == 200
    cats = cat_resp.json()["data"]
    assert len(cats) >= 5

    # Events catalogue
    ev_resp = await client.get("/api/v1/public/editions/parallax-2026/events")
    assert ev_resp.status_code == 200
    events = ev_resp.json()["data"]
    assert len(events) >= 10
    slugs = [e["slug"] for e in events]
    assert "hackathon" in slugs
    assert "coding-competition" in slugs


@pytest.mark.asyncio
async def test_public_schedule(client: AsyncClient):
    resp = await client.get("/api/v1/public/editions/parallax-2026/schedule")
    assert resp.status_code == 200
    days = resp.json()["data"]
    assert len(days) >= 1
