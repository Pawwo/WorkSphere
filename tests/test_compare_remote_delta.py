from scripts.compare_remote_offers import _remote_delta, load_remote_csv, norm_url


def test_norm_url_pracuj_id():
    url = "https://www.pracuj.pl/praca/foo,oferta,1004894101"
    assert norm_url(url) == "pracuj:1004894101"


def test_norm_url_linkedin_id():
    url = "https://pl.linkedin.com/jobs/view/director-at-acme-4426788391"
    assert norm_url(url) == "linkedin:4426788391"


def test_remote_delta_new_keys_only():
    prev = load_remote_csv("URL,Score,Verdict,Title,Company\nhttps://a.com,80,✅,A,Co\n")
    curr = load_remote_csv(
        "URL,Score,Verdict,Title,Company\n"
        "https://a.com,80,✅,A,Co\n"
        "https://b.com,70,🟨,B,Co\n"
    )
    delta = _remote_delta(prev, curr)
    assert len(delta) == 1
    assert delta[norm_url("https://b.com")].title == "B"
