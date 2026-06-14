"""RocketJobs batch circuit breaker."""

from app.services.scrape.batch_context import BatchContext


def test_circuit_breaker_opens_after_three_timeouts(tmp_path):
    from app.config import Settings

    data = tmp_path / "data"
    data.mkdir()
    (data / "job_scraper").mkdir()
    settings = Settings().model_copy(update={"data_dir": data.resolve()})
    ctx = BatchContext(settings)

    ctx.record_rocketjobs_timeout()
    ctx.record_rocketjobs_timeout()
    assert not ctx.rocketjobs_circuit_open

    ctx.record_rocketjobs_timeout()
    assert ctx.rocketjobs_circuit_open
    assert ctx.rocketjobs_timeouts == 3
