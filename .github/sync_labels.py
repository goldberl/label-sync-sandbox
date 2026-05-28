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


# From the API docs:
# > Pull requests are a type of issue. Any actions that are available in both
# > pull requests and issues, like managing assignees, labels, and milestones,
# > are handled by the REST API to manage issues.
# https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10
def add_label(repo, number, label):
    """Add a single label to a PR or issue."""
    gh("api", "-X", "POST", f"/repos/{repo}/issues/{number}/labels",
       "--input", "-", input=json.dumps({"labels": [label]}))


def remove_label(repo, number, label):
    """Remove a single label from a PR or issue."""
    gh("api", "-X", "DELETE", f"/repos/{repo}/issues/{number}/labels/{label}")


def get_linked_pr_numbers(issue_number):
    """Return a list of PR number strings linked to the given issue."""
    pr_list_raw = gh(
        "pr", "list",
        "--search", f"fixes #{issue_number}",
        "--json", "number",
        "-q", ".[].number",
    )
    return pr_list_raw.splitlines() if pr_list_raw else []


def sync_pr_label_to_issue(repo, pr_number, action, label, pr_body):
    match = LINKED_ISSUE_RE.search(pr_body or "")
    if not match:
        print("No linked issue found in the PR description. Skipping sync.")
        return

    issue_num = match.group(2)
    if action == "labeled":
        add_label(repo, issue_num, label)
    elif action == "unlabeled":
        remove_label(repo, issue_num, label)


def sync_issue_label_to_prs(repo, issue_number, action, label):
    pr_numbers = get_linked_pr_numbers(issue_number)
    for pr_num in pr_numbers:
        if action == "labeled":
            add_label(repo, pr_num, label)
        elif action == "unlabeled":
            remove_label(repo, pr_num, label)


def main(event_name, repo, event):
    print(f"Event: {json.dumps(event)}")

    action = event["action"]
    if action not in ("labeled", "unlabeled"):
        print(f"Action '{action}' does not require label sync. Skipping.")
        sys.exit(0)

    label = event["label"]["name"]

    if "pull_request" in event:
        pr = event["pull_request"]
        sync_pr_label_to_issue(
            repo=repo,
            pr_number=pr["number"],
            action=action,
            label=label,
            pr_body=pr.get("body", ""),
        )

    elif "issue" in event:
        issue = event["issue"]
        sync_issue_label_to_prs(
            repo=repo,
            issue_number=issue["number"],
            action=action,
            label=label,
        )

    else:
        print(f"Unsupported event payload: {event_name}")
        sys.exit(1)


if __name__ == "__main__":
    with open(os.environ["GITHUB_EVENT_PATH"]) as f:
        event = json.load(f)

    main(
        event_name=os.environ["GITHUB_EVENT_NAME"],
        repo=os.environ["GITHUB_REPOSITORY"],
        event=event,
    )
