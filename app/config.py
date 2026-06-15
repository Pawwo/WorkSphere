from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = Field(default="http://127.0.0.1:8006/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="your-model-name", alias="LLM_MODEL")
    llm_model_file: str = Field(default="your-model-name", alias="LLM_MODEL_FILE")
    llm_api_key: str = Field(default="unused", alias="LLM_API_KEY")
    llm_max_tokens: int = Field(default=512, alias="LLM_MAX_TOKENS")
    llm_context_size: int = Field(default=4096, alias="LLM_CONTEXT_SIZE")
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")
    llm_timeout_seconds: int = Field(default=180, alias="LLM_TIMEOUT_SECONDS")
    llm_concurrency: int = Field(default=1, alias="LLM_CONCURRENCY")
    llm_inference_probe_enabled: bool = Field(default=True, alias="LLM_INFERENCE_PROBE_ENABLED")
    llm_inference_probe_cache_seconds: int = Field(
        default=90, alias="LLM_INFERENCE_PROBE_CACHE_SECONDS"
    )
    scrape_llm_fit_limit: int = Field(default=40, alias="SCRAPE_LLM_FIT_LIMIT")
    scrape_highlights_max_per_run: int = Field(default=10, alias="SCRAPE_HIGHLIGHTS_MAX_PER_RUN")

    searxng_base_url: str = Field(default="http://127.0.0.1:8888", alias="SEARXNG_BASE_URL")
    searxng_language: str = Field(default="pl", alias="SEARXNG_LANGUAGE")
    searxng_timeout_seconds: int = Field(default=15, alias="SEARXNG_TIMEOUT_SECONDS")

    data_dir: Path = Field(default=ROOT / "data", alias="DATA_DIR")
    bun_path: str = Field(default="bun", alias="BUN_PATH")
    repo_root: Path = Field(default=ROOT, alias="REPO_ROOT")

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8080, alias="PORT")
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    scrapers_skills_dir: str = ".agents/skills"
    scrapers_default_days: int = 14
    scrapers_default_limit: int = 20
    scrapers_parallel_limit: int = 4
    scrapers_portal_timeout_seconds: int = 90
    scrapers_portal_timeouts: Dict[str, int] = Field(default_factory=dict)
    scrapers_retry_on_timeout: int = 1
    scrapers_batch_query_parallelism: int = 2
    scrapers_max_age_hours: int = 48
    scrapers_strict_freshness: bool = True
    scrapers_default_portal_profile: str = "full"
    scrapers_portal_profiles: Dict[str, List[str]] = Field(default_factory=dict)
    scrapers_parallel_tier_groups: bool = True
    scrapers_smart_portal_routing: bool = True
    scrapers_linkedin_batch_subqueries: int = 1
    scrapers_batch_fit_mode: str = "llm"
    scrapers_portal_strict_freshness: Dict[str, bool] = Field(default_factory=dict)
    scrapers_linkedin_detail_limit: int = 0
    scrapers_linkedin_pages: int = 1
    scrapers_disabled_portals: List[str] = Field(default_factory=list)

    salary_b2b_threshold_pln: int = 25000
    salary_benchmarks_file: str = "data/salary_benchmarks_pl.json"

    latex_bin_dir: Optional[Path] = Field(default=None, alias="LATEX_BIN_DIR")
    cv_renderer: str = Field(default="html", alias="CV_RENDERER")

    ats_min_keyword_coverage: float = 0.70
    ats_bold_keywords_in_bullets: bool = True
    ats_truth_guard_strict: bool = True
    ats_max_experience_llm_batches: int = 2
    ats_enrich_pm_roles: bool = True
    ats_summary_min_lead_keywords: int = 2

    pipeline_fast_draft: bool = Field(default=True, alias="PIPELINE_FAST_DRAFT")
    pipeline_interview_prep_enabled: bool = Field(
        default=False, alias="PIPELINE_INTERVIEW_PREP_ENABLED"
    )
    pipeline_stale_task_seconds: int = Field(default=300, alias="PIPELINE_STALE_TASK_SECONDS")
    pipeline_llm_warm_cache_seconds: int = Field(
        default=300, alias="PIPELINE_LLM_WARM_CACHE_SECONDS"
    )
    pipeline_llm_warm_fast_trust: bool = Field(
        default=True, alias="PIPELINE_LLM_WARM_FAST_TRUST"
    )
    pipeline_parallel_cover: bool = Field(default=True, alias="PIPELINE_PARALLEL_COVER")

    @property
    def profile_dir(self) -> Path:
        return self.data_dir / "profile"

    @property
    def job_scraper_dir(self) -> Path:
        return self.data_dir / "job_scraper"

    @property
    def skills_path(self) -> Path:
        return self.repo_root / self.scrapers_skills_dir

    @property
    def seen_jobs_path(self) -> Path:
        return self.job_scraper_dir / "seen_jobs.json"

    @property
    def tracker_path(self) -> Path:
        return self.data_dir / "job_search_tracker.csv"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"


def _merge_yaml_into_settings(settings: Settings) -> Settings:
    yaml_path = ROOT / "config.yaml"
    if not yaml_path.exists():
        return settings
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    llm = raw.get("llm", {})
    search = raw.get("search", {})
    scrapers = raw.get("scrapers", {})
    paths = raw.get("paths", {})
    server = raw.get("server", {})

    updates = {}
    if llm.get("base_url"):
        updates["llm_base_url"] = llm["base_url"]
    if llm.get("model"):
        updates["llm_model"] = llm["model"]
    if llm.get("model_file"):
        updates["llm_model_file"] = llm["model_file"]
    if llm.get("api_key"):
        updates["llm_api_key"] = llm["api_key"]
    if llm.get("max_tokens"):
        updates["llm_max_tokens"] = llm["max_tokens"]
    if llm.get("context_size"):
        updates["llm_context_size"] = llm["context_size"]
    if llm.get("temperature") is not None:
        updates["llm_temperature"] = llm["temperature"]
    if llm.get("timeout_seconds"):
        updates["llm_timeout_seconds"] = llm["timeout_seconds"]
    if llm.get("concurrency") is not None:
        updates["llm_concurrency"] = int(llm["concurrency"])
    if llm.get("inference_probe_enabled") is not None:
        updates["llm_inference_probe_enabled"] = bool(llm["inference_probe_enabled"])
    if llm.get("inference_probe_cache_seconds"):
        updates["llm_inference_probe_cache_seconds"] = int(llm["inference_probe_cache_seconds"])
    if search.get("searxng_base_url"):
        updates["searxng_base_url"] = search["searxng_base_url"]
    if search.get("default_language"):
        updates["searxng_language"] = search["default_language"]
    if search.get("timeout_seconds"):
        updates["searxng_timeout_seconds"] = search["timeout_seconds"]
    if paths.get("data_dir"):
        updates["data_dir"] = ROOT / paths["data_dir"].lstrip("./")
    if scrapers.get("skills_dir"):
        updates["scrapers_skills_dir"] = scrapers["skills_dir"]
    if scrapers.get("default_days"):
        updates["scrapers_default_days"] = scrapers["default_days"]
    if scrapers.get("default_limit"):
        updates["scrapers_default_limit"] = scrapers["default_limit"]
    if scrapers.get("parallel_limit"):
        updates["scrapers_parallel_limit"] = scrapers["parallel_limit"]
    if scrapers.get("portal_timeout_seconds"):
        updates["scrapers_portal_timeout_seconds"] = scrapers["portal_timeout_seconds"]
    if scrapers.get("portal_timeouts"):
        updates["scrapers_portal_timeouts"] = {
            str(k): int(v) for k, v in scrapers["portal_timeouts"].items()
        }
    if scrapers.get("retry_on_timeout") is not None:
        updates["scrapers_retry_on_timeout"] = scrapers["retry_on_timeout"]
    if scrapers.get("batch_query_parallelism"):
        updates["scrapers_batch_query_parallelism"] = scrapers["batch_query_parallelism"]
    if scrapers.get("max_age_hours"):
        updates["scrapers_max_age_hours"] = scrapers["max_age_hours"]
    if scrapers.get("strict_freshness") is not None:
        updates["scrapers_strict_freshness"] = scrapers["strict_freshness"]
    if scrapers.get("default_portal_profile"):
        updates["scrapers_default_portal_profile"] = scrapers["default_portal_profile"]
    if scrapers.get("portal_profiles"):
        updates["scrapers_portal_profiles"] = {
            str(k): list(v) for k, v in scrapers["portal_profiles"].items()
        }
    if scrapers.get("linkedin_detail_limit"):
        updates["scrapers_linkedin_detail_limit"] = scrapers["linkedin_detail_limit"]
    if scrapers.get("linkedin_pages"):
        updates["scrapers_linkedin_pages"] = scrapers["linkedin_pages"]
    if scrapers.get("parallel_tier_groups") is not None:
        updates["scrapers_parallel_tier_groups"] = scrapers["parallel_tier_groups"]
    if scrapers.get("smart_portal_routing") is not None:
        updates["scrapers_smart_portal_routing"] = scrapers["smart_portal_routing"]
    if scrapers.get("linkedin_batch_subqueries"):
        updates["scrapers_linkedin_batch_subqueries"] = scrapers["linkedin_batch_subqueries"]
    if scrapers.get("batch_fit_mode"):
        updates["scrapers_batch_fit_mode"] = scrapers["batch_fit_mode"]
    if scrapers.get("llm_fit_limit") is not None:
        updates["scrape_llm_fit_limit"] = int(scrapers["llm_fit_limit"])
    if scrapers.get("highlights_max_per_run") is not None:
        updates["scrape_highlights_max_per_run"] = int(scrapers["highlights_max_per_run"])
    if scrapers.get("portal_strict_freshness"):
        updates["scrapers_portal_strict_freshness"] = {
            str(k): bool(v) for k, v in scrapers["portal_strict_freshness"].items()
        }
    if scrapers.get("disabled_portals"):
        updates["scrapers_disabled_portals"] = list(scrapers["disabled_portals"])
    salary = raw.get("salary", {})
    if salary.get("b2b_monthly_threshold_pln"):
        updates["salary_b2b_threshold_pln"] = salary["b2b_monthly_threshold_pln"]
    if salary.get("benchmarks_file"):
        updates["salary_benchmarks_file"] = salary["benchmarks_file"]
    if server.get("cors_origins"):
        updates["cors_origins"] = server["cors_origins"]
    if server.get("host"):
        updates["host"] = server["host"]
    if server.get("port"):
        updates["port"] = server["port"]
    ats = raw.get("ats", {})
    if ats.get("min_keyword_coverage") is not None:
        updates["ats_min_keyword_coverage"] = float(ats["min_keyword_coverage"])
    if ats.get("bold_keywords_in_bullets") is not None:
        updates["ats_bold_keywords_in_bullets"] = bool(ats["bold_keywords_in_bullets"])
    if ats.get("truth_guard_strict") is not None:
        updates["ats_truth_guard_strict"] = bool(ats["truth_guard_strict"])
    if ats.get("max_experience_llm_batches") is not None:
        updates["ats_max_experience_llm_batches"] = int(ats["max_experience_llm_batches"])
    if ats.get("enrich_pm_roles") is not None:
        updates["ats_enrich_pm_roles"] = bool(ats["enrich_pm_roles"])
    if ats.get("summary_min_lead_keywords") is not None:
        updates["ats_summary_min_lead_keywords"] = int(ats["summary_min_lead_keywords"])
    pipeline = raw.get("pipeline", {})
    if pipeline.get("fast_draft") is not None:
        updates["pipeline_fast_draft"] = bool(pipeline["fast_draft"])
    if pipeline.get("interview_prep_enabled") is not None:
        updates["pipeline_interview_prep_enabled"] = bool(pipeline["interview_prep_enabled"])
    if pipeline.get("stale_task_seconds") is not None:
        updates["pipeline_stale_task_seconds"] = int(pipeline["stale_task_seconds"])
    if pipeline.get("llm_warm_cache_seconds") is not None:
        updates["pipeline_llm_warm_cache_seconds"] = int(pipeline["llm_warm_cache_seconds"])
    if pipeline.get("llm_warm_fast_trust") is not None:
        updates["pipeline_llm_warm_fast_trust"] = bool(pipeline["llm_warm_fast_trust"])
    if pipeline.get("parallel_cover") is not None:
        updates["pipeline_parallel_cover"] = bool(pipeline["parallel_cover"])
    if pipeline.get("max_experience_llm_batches") is not None:
        updates["ats_max_experience_llm_batches"] = int(pipeline["max_experience_llm_batches"])

    merged = settings.model_copy(update=updates) if updates else settings
    return merged


def _resolve_paths(settings: Settings) -> Settings:
    repo = settings.repo_root
    if not repo.is_absolute():
        repo = (ROOT / repo).resolve()
    data = settings.data_dir
    if not data.is_absolute():
        data = (repo / data).resolve()
    latex_bin = settings.latex_bin_dir
    if latex_bin and not latex_bin.is_absolute():
        latex_bin = (repo / latex_bin).resolve()
    elif latex_bin is None:
        import platform

        tinytex = Path.home() / ".TinyTeX" / "bin" / f"{platform.machine()}-linux"
        if (tinytex / "lualatex").exists():
            latex_bin = tinytex
    return settings.model_copy(
        update={"repo_root": repo, "data_dir": data, "latex_bin_dir": latex_bin}
    )


@lru_cache
def get_settings() -> Settings:
    return _resolve_paths(_merge_yaml_into_settings(Settings()))


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def config_yaml_path() -> Path:
    return ROOT / "config.yaml"


def update_yaml_llm_settings(
    *,
    base_url: str | None = None,
    model: str | None = None,
    model_file: str | None = None,
    api_key: str | None = None,
    context_size: int | None = None,
) -> None:
    """Persist LLM endpoint fields to config.yaml and refresh settings cache."""
    path = config_yaml_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(raw, dict):
        raw = {}
    llm = raw.setdefault("llm", {})
    if base_url is not None:
        llm["base_url"] = base_url.rstrip("/")
    if model is not None:
        llm["model"] = model.strip()
    if model_file is not None:
        llm["model_file"] = model_file.strip()
    elif model is not None:
        llm["model_file"] = model.strip()
    if api_key is not None:
        llm["api_key"] = api_key
    if context_size is not None:
        llm["context_size"] = int(context_size)
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    clear_settings_cache()


def update_yaml_llm_base_url(base_url: str) -> None:
    """Persist LLM base_url to config.yaml and refresh settings cache."""
    update_yaml_llm_settings(base_url=base_url)
