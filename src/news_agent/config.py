"""Sozlamalar: .env dan sirlar, YAML'dan manbalar va qiziqish profili."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
STATE_DIR = PROJECT_ROOT / "state"
DIGESTS_DIR = PROJECT_ROOT / "digests"


class Settings(BaseSettings):
    """.env va muhit o'zgaruvchilaridan o'qiladi."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    gemini_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""

    # --- Instagram ---
    instagram_access_token: str = ""
    instagram_user_id: str = ""
    # Rasmlar shu repo'ning o'zida saqlanadi va raw.githubusercontent.com orqali
    # Instagram'ga beriladi. Repo OCHIQ bo'lishi shart — Meta rasmni o'zi yuklab
    # oladi va autentifikatsiya qila olmaydi.
    assets_repo: str = "imxumoyun/news-agent"
    assets_branch: str = "main"
    # Rasm yuklangandan keyin CDN'da paydo bo'lishini kutish (soniya).
    assets_wait_timeout: float = 90.0

    # Model ID'lari konfiguratsiyada — Google ularni tez-tez yangilaydi.
    # Uchalasi ham flash-lite: bepul tarif chegarasiga sig'ish uchun.
    # Billing yoqsangiz ANALYST_MODEL=gemini-3.6-flash qilib qo'ying —
    # o'zbekcha matn sifati sezilarli yaxshilanadi.
    curator_model: str = "gemini-3.5-flash-lite"
    analyst_model: str = "gemini-3.5-flash-lite"
    editor_model: str = "gemini-3.5-flash-lite"
    caption_model: str = "gemini-3.5-flash-lite"

    # Pipeline sozlamalari
    window_hours: int = 14  # kuniga 2 marta ishlaydi, biroz ustma-ust tushsin
    max_candidates: int = 160  # Curator'ga beriladigan maksimal maqola
    analyst_concurrency: int = 2
    # Daqiqasiga ruxsat etilgan chaqiruvlar soni. Bepul tarifda 5.
    # Pullik tarifga o'tsangiz .env da RPM_LIMIT=60 qilib qo'ying — ancha tezlashadi.
    rpm_limit: int = 5
    fetch_timeout: float = 20.0
    posted_retention_days: int = 30

    def require(self, *names: str) -> None:
        """Kerakli sirlar to'ldirilganini tekshiradi."""
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise RuntimeError(
                ".env da quyidagi qiymatlar yo'q: "
                + ", ".join(n.upper() for n in missing)
                + "\n.env.example faylidan nusxa oling va to'ldiring."
            )


class Source(BaseModel):
    name: str
    url: str
    category: str
    weight: float = 0.7
    # Bitta manba butun ro'yxatni bosib ketmasligi uchun chegara.
    max_items: int = 15


class Profile(BaseModel):
    audience: str
    interests: dict[str, list[str]] = Field(default_factory=dict)
    exclude: list[str] = Field(default_factory=list)
    max_items: int = 11
    min_items: int = 5

    def as_prompt_block(self) -> str:
        """Profilni prompt uchun o'qiladigan matnga aylantiradi."""
        lines = [f"AUDITORIYA: {self.audience.strip()}", ""]
        labels = {"high": "YUQORI muhimlik", "medium": "O'RTA muhimlik", "low": "PAST muhimlik"}
        for key, label in labels.items():
            items = self.interests.get(key)
            if items:
                lines.append(f"{label}:")
                lines.extend(f"  - {item}" for item in items)
                lines.append("")
        if self.exclude:
            lines.append("TANLANMASIN:")
            lines.extend(f"  - {item}" for item in self.exclude)
        return "\n".join(lines).strip()


class StylePattern(BaseModel):
    name: str
    shape: str


class Style(BaseModel):
    """Matn qanday yozilishi — profile.yaml esa nima haqida yozilishini belgilaydi."""

    voice: str
    rules: list[str] = Field(default_factory=list)
    banned: list[str] = Field(default_factory=list)
    length: dict[str, int] = Field(default_factory=dict)
    patterns: list[StylePattern] = Field(default_factory=list)

    @property
    def item_min(self) -> int:
        return self.length.get("item_min", 180)

    @property
    def item_max(self) -> int:
        return self.length.get("item_max", 380)

    def as_prompt_block(self) -> str:
        lines = [f"OVOZ: {self.voice.strip()}", ""]
        if self.rules:
            lines.append("QOIDALAR:")
            lines.extend(f"  - {rule}" for rule in self.rules)
            lines.append("")
        if self.banned:
            lines.append("MAN ETILGAN:")
            lines.extend(f"  - {item}" for item in self.banned)
            lines.append("")
        if self.patterns:
            lines.append("SHAKLLAR (birini tanla, yangilikka mosini):")
            for pattern in self.patterns:
                lines.append(f"  [{pattern.name}]")
                lines.extend(f"    {row}" for row in pattern.shape.strip().splitlines())
                lines.append("")
        return "\n".join(lines).strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def load_style(path: Path | None = None) -> Style:
    data = yaml.safe_load((path or CONFIG_DIR / "style.yaml").read_text(encoding="utf-8"))
    return Style(**data)


@lru_cache(maxsize=1)
def load_sources(path: Path | None = None) -> list[Source]:
    data = yaml.safe_load((path or CONFIG_DIR / "sources.yaml").read_text(encoding="utf-8"))
    return [Source(**item) for item in data["sources"]]


@lru_cache(maxsize=1)
def load_profile(path: Path | None = None) -> Profile:
    data = yaml.safe_load((path or CONFIG_DIR / "profile.yaml").read_text(encoding="utf-8"))
    return Profile(**data)
