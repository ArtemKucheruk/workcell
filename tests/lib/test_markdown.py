from workcell.lib.markdown import render_with_headings


def test_heading_gets_id():  # 029 AC1
    html, headings = render_with_headings("## fctl serve\n\ntext\n")
    assert '<h2 id="fctl-serve">fctl serve</h2>' in html
    assert headings == [{"id": "fctl-serve", "text": "fctl serve", "level": 2}]


def test_code_span_and_level():  # 029 AC2
    html, headings = render_with_headings("## Using `fctl` with Docker\n")
    assert headings == [{"id": "using-fctl-with-docker", "text": "Using fctl with Docker", "level": 2}]
    assert '<h2 id="using-fctl-with-docker">Using <code>fctl</code> with Docker</h2>' in html
    assert render_with_headings("### FCTL_URL and FCTL_HOME\n")[1] == [
        {"id": "fctl-url-and-fctl-home", "text": "FCTL_URL and FCTL_HOME", "level": 3}]


def test_raw_html_off():  # 029 AC3
    html, headings = render_with_headings("## <b>x</b>\n\n<script>alert(1)</script>\n")
    assert "<b>" not in html and "<script" not in html
    assert "&lt;script&gt;" in html
    assert [h["text"] for h in headings] == ["<b>x</b>"]


def test_fenced_heading_is_no_heading():  # 029 AC4
    assert render_with_headings("```sh\n## not a heading\n```\n")[1] == []
