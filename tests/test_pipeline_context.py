from app.models.apply import ApplyRequest
from app.services.pipeline.context import PipelineContext


def test_pipeline_context_defaults():
    ctx = PipelineContext(
        request=ApplyRequest(url="https://example.com/job"),
        application_id=1,
        run_id=2,
    )
    assert ctx.files == []
    assert ctx.parsed is None
    assert ctx.task_id is None
