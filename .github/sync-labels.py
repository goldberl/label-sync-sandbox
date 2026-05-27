#!/usr/bin/env python3
"""Bi-directional label sync between PRs and linked issues."""

import json
import os
import re
import subprocess
import sys

LINKED_ISSUE_RE = re.compile(
    r'(?i)(closes|closed|fixes|fixed|resolves|resolved)\s+#(\d+)'
)


def gh(*args, input=None):
    """Run a gh CLI command and return stdout as a string."""
    print("gh", *args)
    if input is not None:
        print("  stdin:", input)
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        check=True,
        text=True,
        input=input,
    )
    return result.stdout.strip()


def gh_json(*args):
    """Run a gh CLI command and parse the output as JSON."""
    return json.loads(gh(*args))


def gh_api_put(endpoint, input, *args):
    """Send a PUT request via the gh API with JSON piped to stdin."""
    gh("api", "-X", "PUT", endpoint, "--input", "-", *args, input=input)


def view_labels(item_type, number):
    """Return the list of label names on a PR or issue."""
    return gh_json(
        item_type, "view", str(number),
        "--json", "labels",
        "-q", "[.labels[].name]",
    )


def set_labels(repo, number, labels):
    """Overwrite the labels on a PR or issue."""
    gh_api_put(
        f"/repos/{repo}/issues/{number}/labels",
        json.dumps(labels),
    )


def sync_pr_to_issue(repo, pr_number, pr_body):
    match = LINKED_ISSUE_RE.search(pr_body)
    if not match:
        print("No linked issue found in the PR description. Skipping sync.")
        return

    issue_num = match.group(2)
    pr_labels = view_labels("pr", pr_number)

    if pr_labels:
        set_labels(repo, issue_num, pr_labels)
    else:
        issue_labels = view_labels("issue", issue_num)
        set_labels(repo, pr_number, issue_labels)


def sync_issue_to_prs(repo, issue_number):
    pr_list_raw = gh(
        "pr", "list",
        "--search", f"fixes #{issue_number}",
        "--json", "number",
        "-q", ".[].number",
    )
    pr_numbers = pr_list_raw.splitlines() if pr_list_raw else []

    labels = view_labels("issue", issue_number)

    for pr_num in pr_numbers:
        set_labels(repo, pr_num, labels)


def main():
    event_name = os.environ["GITHUB_EVENT_NAME"]
    repo = os.environ["GITHUB_REPOSITORY"]

    if event_name == "pull_request":
        pr_number = int(os.environ["PR_NUMBER"])
        pr_body = os.environ.get("PR_BODY", "")
        sync_pr_to_issue(repo, pr_number, pr_body)

    elif event_name == "issues":
        issue_number = int(os.environ["ISSUE_NUMBER"])
        sync_issue_to_prs(repo, issue_number)

    else:
        print(f"Unsupported event: {event_name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
