import json
from pathlib import Path

from app.models.jobs import SeenJobEntry
from app.services.pi_gap_sync import PiJob, mark_only_worksphere_deep_eval, norm_url, sync_pi_metadata


def test_sync_pi_metadata_updates_existing(tmp_path: Path):
    seen_path = tmp_path / "seen_jobs.json"
    url = "https://www.pracuj.pl/praca/foo,oferta,1004894101"
    seen_path.write_text(
        json.dumps(
            {
                "seen": {
                    url: SeenJobEntry(
                        title="Director",
                        company="Aon",
                        url=url,
                        first_seen="2026-06-11",
                        fit="medium",
                    ).model_dump()
                }
            }
        ),
        encoding="utf-8",
    )
    key = norm_url(url)
    n = sync_pi_metadata(
        {key: PiJob(url, "Director", "Aon", 69, "🟥", "rag", "pracuj")},
        seen_path,
    )
    assert n == 1
    data = json.loads(seen_path.read_text())
    entry = next(iter(data["seen"].values()))
    assert entry["pi_score"] == 69
    assert entry["pi_verdict"] == "🟥"


def test_mark_only_worksphere_deep_eval(tmp_path: Path):
    seen_path = tmp_path / "seen_jobs.json"
    ws_url = "https://pl.linkedin.com/jobs/view/studio-director-at-partyhat-4423187921"
    seen_path.write_text(
        json.dumps(
            {
                "seen": {
                    ws_url: SeenJobEntry(
                        title="Studio Director",
                        company="Partyhat",
                        url=ws_url,
                        first_seen="2026-06-11",
                    ).model_dump()
                }
            }
        ),
        encoding="utf-8",
    )
    n = mark_only_worksphere_deep_eval(
        {norm_url(ws_url)},
        set(),
        seen_path,
    )
    assert n == 1
    entry = json.loads(seen_path.read_text())["seen"][ws_url]
    assert entry["needs_deep_eval"] is True
