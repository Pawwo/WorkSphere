import pytest

from app.models.jobs import JobCard
from app.services.scrape.fit import fit_jobs_parallel


class _Salary:
    threshold_pln = 25000

    def assess(self, **kwargs):
        from app.services.salary_service import SalaryAssessment

        return SalaryAssessment(
            salary_raw="",
            monthly_b2b_min=None,
            monthly_b2b_max=None,
            monthly_b2b_median=None,
            source="missing",
            meets_threshold=False,
            reason="",
        )

    def adjust_fit(self, fit, assessment, threshold):
        return fit


class _LLM:
    calls = 0

    async def quick_fit(self, profile_excerpt, job):
        type(self).calls += 1
        return "high"


class _Settings:
    scrape_llm_fit_limit = 0


class _Service:
    settings = _Settings()
    salary = _Salary()
    llm = _LLM()


@pytest.mark.asyncio
async def test_unlimited_llm_fit_calls_all_jobs(tmp_path):
    from app.services.fit_cache import clear_fit_cache, configure_fit_cache_for_tests

    configure_fit_cache_for_tests(tmp_path / "fit_cache.json")
    clear_fit_cache()
    _LLM.calls = 0
    jobs = [
        (
            JobCard(
                id="1",
                title="Head of Operations",
                company="Acme",
                url=f"https://example.com/{i}",
            ),
            "pracuj",
        )
        for i in range(8)
    ]
    results = await fit_jobs_parallel(_Service(), jobs, "profile", True, allow_llm=True)
    assert len(results) == 8
    assert _LLM.calls == 8
