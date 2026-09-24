from skyline.links import code_url, github_base


def test_ssh_remote_links_to_a_line_range():
    remote = "git@github.com:acme/widgets.git"
    assert github_base(remote) == "https://github.com/acme/widgets"
    url = code_url(remote, "abc123", "src/pay.py", 10, 18)
    assert url == "https://github.com/acme/widgets/blob/abc123/src/pay.py#L10-L18"


def test_other_hosts_are_not_linked():
    assert code_url("https://gitlab.com/acme/widgets.git", "abc", "a.py", 1) is None
