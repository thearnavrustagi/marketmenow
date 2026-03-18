from __future__ import annotations

from pathlib import Path

from adapters.email.models import ContactRow, SendResult
from adapters.email.sender import (
    _build_message,
    parse_template,
    read_contacts,
    render_email,
)

# ---------------------------------------------------------------------------
# parse_template
# ---------------------------------------------------------------------------


class TestParseTemplate:
    def test_with_front_matter(self) -> None:
        raw = "---\nsubject: Hello {{ name }}\ntitle: Welcome\n---\n<h1>Hi</h1>"
        meta, html = parse_template(raw)
        assert meta["subject"] == "Hello {{ name }}"
        assert meta["title"] == "Welcome"
        assert html.strip() == "<h1>Hi</h1>"

    def test_without_front_matter(self) -> None:
        raw = "<h1>No front matter</h1>"
        meta, html = parse_template(raw)
        assert meta == {}
        assert html == raw

    def test_empty_front_matter(self) -> None:
        raw = "---\n\n---\n<p>Body</p>"
        meta, html = parse_template(raw)
        assert meta == {}
        assert html.strip() == "<p>Body</p>"


# ---------------------------------------------------------------------------
# read_contacts
# ---------------------------------------------------------------------------


class TestReadContacts:
    def test_reads_range(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "contacts.csv"
        csv_file.write_text("email,name\nalice@e.com,Alice\nbob@e.com,Bob\ncharlie@e.com,Charlie\n")
        contacts = read_contacts(csv_file, 0, 2)
        assert len(contacts) == 2
        assert contacts[0][1].email == "alice@e.com"
        assert contacts[1][1].email == "bob@e.com"

    def test_skips_empty_email(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "contacts.csv"
        csv_file.write_text("email,name\nalice@e.com,Alice\n,NoEmail\nbob@e.com,Bob\n")
        contacts = read_contacts(csv_file, 0, 10)
        emails = [c.email for _, c in contacts]
        assert "" not in emails
        assert len(contacts) == 2

    def test_empty_range(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "contacts.csv"
        csv_file.write_text("email,name\nalice@e.com,Alice\n")
        contacts = read_contacts(csv_file, 5, 10)
        assert contacts == []

    def test_row_index_preserved(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "contacts.csv"
        csv_file.write_text("email,name\na@e.com,A\nb@e.com,B\nc@e.com,C\n")
        contacts = read_contacts(csv_file, 1, 3)
        assert contacts[0][0] == 1
        assert contacts[1][0] == 2


# ---------------------------------------------------------------------------
# render_email
# ---------------------------------------------------------------------------


class TestRenderEmail:
    def test_renders_variables(self) -> None:
        subject, html = render_email(
            "<p>Hello {{ name }}</p>",
            "Welcome {{ name }}",
            {"name": "Alice"},
        )
        assert subject == "Welcome Alice"
        assert "Hello Alice" in html

    def test_no_variables(self) -> None:
        subject, html = render_email("<p>Static</p>", "Static Subject", {})
        assert subject == "Static Subject"
        assert "Static" in html


# ---------------------------------------------------------------------------
# _build_message
# ---------------------------------------------------------------------------


class TestBuildMessage:
    def test_fields(self) -> None:
        msg = _build_message(
            sender="from@e.com",
            to="to@e.com",
            subject="Test",
            html_body="<p>Body</p>",
            bcc="bcc@e.com",
        )
        assert msg["From"] == "from@e.com"
        assert msg["To"] == "to@e.com"
        assert msg["Subject"] == "Test"
        assert msg["Bcc"] == "bcc@e.com"


# ---------------------------------------------------------------------------
# ContactRow
# ---------------------------------------------------------------------------


class TestContactRow:
    def test_template_vars(self) -> None:
        row = ContactRow(email="a@e.com", fields={"name": "Alice", "company": "Acme"})
        tvars = row.template_vars
        assert tvars["email"] == "a@e.com"
        assert tvars["name"] == "Alice"
        assert tvars["company"] == "Acme"

    def test_template_vars_empty_fields(self) -> None:
        row = ContactRow(email="b@e.com")
        assert row.template_vars == {"email": "b@e.com"}


class TestEmailSendResult:
    def test_defaults(self) -> None:
        r = SendResult(row_index=0, email="a@e.com", success=True)
        assert r.error == ""

    def test_with_error(self) -> None:
        r = SendResult(row_index=1, email="a@e.com", success=False, error="timeout")
        assert r.error == "timeout"
