from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.db import init_db
from app.engine import auto_advance, execute_action, new_game
from app.store import GameStore

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "riichi-mahjong-ui" / "dist"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
FRONTEND_ASSETS_DIR = FRONTEND_DIR / "assets"

app = FastAPI(title="单人立直麻将")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
if FRONTEND_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_DIR), name="frontend-assets")
store = GameStore()


class CreateGameRequest(BaseModel):
    player_name: str = Field(default="访客", max_length=32)
    mode: str = Field(default="4P")
    round_length: str = Field(default="EAST")
    rule_profile: str = Field(default="RANKED")
    ai_levels: list[int] = Field(default_factory=lambda: [1, 2, 3])
    enable_koyaku: bool = Field(default=False)
    sanma_scoring_mode: str = Field(default="TSUMO_LOSS")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in {"4P", "3P"}:
            raise ValueError("模式只能是 4P 或 3P")
        return value

    @field_validator("round_length")
    @classmethod
    def validate_round_length(cls, value: str) -> str:
        if value not in {"EAST", "HANCHAN"}:
            raise ValueError("场次只能是 EAST 或 HANCHAN")
        return value

    @field_validator("rule_profile")
    @classmethod
    def validate_rule_profile(cls, value: str) -> str:
        if value not in {"RANKED", "FRIEND", "KOYAKU"}:
            raise ValueError("瑙勫垯妗ｄ綅鍙兘鏄?RANKED銆?FRIEND 鎴?KOYAKU")
        return value

    @field_validator("ai_levels")
    @classmethod
    def validate_levels(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("AI 难度不能为空")
        return [min(3, max(1, int(level))) for level in value]

    @field_validator("sanma_scoring_mode")
    @classmethod
    def validate_sanma_scoring_mode(cls, value: str) -> str:
        if value not in {"TSUMO_LOSS", "NORTH_BISECTION"}:
            raise ValueError("涓夐夯璁″垎鍙兘鏄?TSUMO_LOSS 鎴?NORTH_BISECTION")
        return value


class ActionRequest(BaseModel):
    action_id: str


def public_payload(game: dict) -> dict:
    return {
        **game["public_state"],
        "result_summary": game.get("result_summary"),
        "created_at": game.get("created_at"),
        "updated_at": game.get("updated_at"),
    }


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index() -> Response:
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    return HTMLResponse(
        """
        <html lang="zh-CN">
          <head>
            <meta charset="utf-8" />
            <title>单人立直麻将</title>
          </head>
          <body style="font-family: sans-serif; padding: 32px;">
            <h1>React 前端尚未构建</h1>
            <p>请先在 <code>riichi-mahjong-ui</code> 目录执行 <code>npm.cmd install</code> 和 <code>npm.cmd run build</code>。</p>
          </body>
        </html>
        """,
        status_code=503,
    )


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/games")
def list_games() -> dict:
    return {"items": store.list_games()}


@app.get("/api/games/{game_id}")
def get_game(game_id: str) -> dict:
    game = store.load_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="未找到对局")
    auto_advance(game)
    store.save_game(game)
    return public_payload(game)


@app.delete("/api/games/{game_id}")
def delete_game(game_id: str) -> dict:
    deleted = store.delete_game(game_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="未找到对局")
    return {"ok": True}


@app.post("/api/games")
def create_game(payload: CreateGameRequest) -> dict:
    player_name = payload.player_name.strip() or "访客"
    game = new_game(
        player_name=player_name,
        mode=payload.mode,
        round_length=payload.round_length,
        ai_levels=payload.ai_levels,
        enable_koyaku=payload.enable_koyaku,
        sanma_scoring=payload.sanma_scoring_mode,
        rule_profile_name=payload.rule_profile,
    )
    store.save_game(game)
    return public_payload(game)


@app.post("/api/games/{game_id}/actions")
def game_action(game_id: str, payload: ActionRequest) -> dict:
    game = store.load_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="未找到对局")
    try:
        execute_action(game, payload.action_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.save_game(game)
    return public_payload(game)


@app.get("/api/games/{game_id}/replay")
def game_replay(game_id: str) -> dict:
    replay = store.get_replay(game_id)
    if replay is None:
        raise HTTPException(status_code=404, detail="未找到回放")
    return replay


@app.get("/api/stats/{player_name}")
def player_stats(player_name: str) -> dict:
    return store.get_player_stats(player_name)


@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa_fallback(full_path: str) -> Response:
    if full_path.startswith(("api/", "assets/", "static/")):
        raise HTTPException(status_code=404, detail="未找到资源")
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    raise HTTPException(status_code=503, detail="React 前端尚未构建")
