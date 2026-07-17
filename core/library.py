import aiohttp


async def fetch_library_info(
    url: str,
    *,
    target_id: str,
    cookies: str = "",
) -> dict[str, str]:
    """Fetch library data for a QQ user."""
    headers = {
        "accept": "*/*",
        "referer": url,
        "user-agent": "Mozilla/5.0",
    }
    if cookies:
        headers["Cookie"] = cookies
    async with aiohttp.ClientSession() as session:
        resp = await session.get(
            url=f"{url}/api/query",
            params={"value": target_id},
            headers=headers,
        )
        resp.raise_for_status()
        payload = await resp.json(content_type=None)
        data = payload.get("data")
        if not data:
            raise ValueError(f"library returned empty data for {target_id=}")

        return data
