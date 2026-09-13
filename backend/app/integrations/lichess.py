from __future__ import annotations

import httpx


class LichessOpeningExplorer:
    base_url = "https://explorer.lichess.ovh"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=8.0, headers={"User-Agent": "chess-coach/0.1"})

    def query(self, fen: str, *, source: str, ratings: tuple[int, ...] = (), speeds: tuple[str, ...] = ()) -> dict:
        params: dict[str, str | int] = {"fen": fen, "moves": 12, "topGames": 0, "recentGames": 0}
        if ratings:
            params["ratings"] = ",".join(str(value) for value in ratings)
        if speeds:
            params["speeds"] = ",".join(speeds)
        response = self.client.get(f"{self.base_url}/{source}", params=params)
        response.raise_for_status()
        return response.json()

