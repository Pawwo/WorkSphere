"""Reset service — documents scope clears uploads, application packages, generated CV."""

from pathlib import Path

from app.config import Settings
from app.models.workflow import ResetExecuteRequest, ResetPreviewRequest
from app.services.reset_service import ResetService


def _settings(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    (data / "documents" / "CV").mkdir(parents=True)
    (data / "documents" / "CV" / "resume.pdf").write_bytes(b"pdf")
    (data / "applications" / "acme").mkdir(parents=True)
    (data / "applications" / "acme" / "interview_prep.md").write_text("prep", encoding="utf-8")
    (data / "profile").mkdir(parents=True)
    (data / "profile" / "01-candidate-profile.md").write_text("# filled\n" + "x" * 200, encoding="utf-8")
    (data / "profile" / "search-queries.md").write_text(
        '### Priority 1: COO\n```\n"COO" Szczecin\n```\n', encoding="utf-8"
    )
    (data / "job_scraper").mkdir(parents=True)
    (data / "job_scraper" / "seen_jobs.json").write_text('{"seen":{"u":{}}}', encoding="utf-8")
    repo = tmp_path
    cv = repo / "cv"
    cv.mkdir()
    (cv / "Resume_Test_User_Acme_Corp.tex").write_text("tex", encoding="utf-8")
    (cv / "moderncv.cls").write_text("class", encoding="utf-8")
    cover = repo / "cover_letters"
    cover.mkdir()
    (cover / "Cover_Test_User_Acme_Corp.tex").write_text("tex", encoding="utf-8")
    (cover / "cover.cls").write_text("class", encoding="utf-8")
    return Settings().model_copy(update={"data_dir": data.resolve(), "repo_root": repo.resolve()})


def test_documents_scope_clears_applications_and_generated_cv(tmp_path):
    settings = _settings(tmp_path)
    svc = ResetService(settings)

    preview = svc.preview(ResetPreviewRequest(scope="documents"))
    assert any("applications/acme" in p for p in preview.document_files)
    assert any("Resume_Test_User_Acme_Corp" in p for p in preview.document_files)

    result = svc.execute(ResetExecuteRequest(scope="documents", confirmation="RESET"))
    assert not (settings.data_dir / "applications" / "acme").exists()
    assert not (settings.repo_root / "cv" / "Resume_Test_User_Acme_Corp.tex").exists()
    assert (settings.repo_root / "cv" / "moderncv.cls").exists()
    assert not (settings.repo_root / "cover_letters" / "Cover_Test_User_Acme_Corp.tex").exists()
    assert (settings.repo_root / "cover_letters" / "cover.cls").exists()
    assert not (settings.data_dir / "documents" / "CV" / "resume.pdf").exists()
    assert "data/profile" not in " ".join(result.cleared)


def test_profile_scope_leaves_documents(tmp_path):
    settings = _settings(tmp_path)
    svc = ResetService(settings)
    svc.execute(ResetExecuteRequest(scope="profile", confirmation="RESET"))
    assert (settings.data_dir / "applications" / "acme" / "interview_prep.md").exists()
    assert (settings.repo_root / "cv" / "Resume_Test_User_Acme_Corp.tex").exists()
    sq = (settings.data_dir / "profile" / "search-queries.md").read_text(encoding="utf-8")
    assert "COO" not in sq
    assert "Query Categories" in sq


def test_all_scope_clears_profile_and_documents(tmp_path):
    settings = _settings(tmp_path)
    (settings.job_scraper_dir / "triage_result.json").write_text("{}", encoding="utf-8")
    svc = ResetService(settings)
    result = svc.execute(ResetExecuteRequest(scope="all", confirmation="RESET"))
    assert not (settings.data_dir / "applications" / "acme").exists()
    assert "data/profile/01-candidate-profile.md" in result.cleared
    assert "data/job_scraper/triage_result.json" in result.cleared
