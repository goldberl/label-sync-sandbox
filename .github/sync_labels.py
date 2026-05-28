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

LABEL_ACTIONS = ["labeled", "unlabeled"]


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
    return json.loads(result.stdout) if result.stdout.strip() else None


# From the API docs:
# > Pull requests are a type of issue. Any actions that are available in both
# > pull requests and issues, like managing assignees, labels, and milestones,
# > are handled by the REST API to manage issues.
# https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10
def issue_labels(repo, number):
    return gh("api", "-X", "GET", f"/repos/{repo}/issues/{number}/labels")


def add_label(repo, number, *labels):
    """Add a single label or multiple labels to a PR or issue."""
    gh("api", "-X", "POST", f"/repos/{repo}/issues/{number}/labels",
       "--input", "-", input=json.dumps({"labels": labels}))


def remove_label(repo, number, label):
    """Remove a single label from a PR or issue."""
    gh("api", "-X", "DELETE", f"/repos/{repo}/issues/{number}/labels/{label}")


def get_linked_pr_numbers(issue_number):
    """Return a list of PR number strings linked to the given issue."""
    pr_list_raw = gh(
        "pr", "list",
        "--search", f"fixes #{issue_number}",
        "--json", "number",
    )
    return [pr["number"] for pr in pr_list_raw]


def linked_issue_numbers(pr_body):
    match = LINKED_ISSUE_RE.search(pr_body)
    if not match:
        return []
    else:
        return [match.group(2)]


def sync_pr_label_to_issue(repo, pr_number, action, label, pr_body):
    issue_nums = linked_issue_numbers(pr_body)
    if len(issue_nums) <= 0:
        print("No linked issue found in the PR description. Skipping sync.")
        return

    for issue_num in issue_nums:
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

    if action in LABEL_ACTIONS and "pull_request" in event:
        pr = event["pull_request"]
        sync_pr_label_to_issue(
            repo=repo,
            pr_number=pr["number"],
            action=action,
            label=event["label"]["name"],
            pr_body=pr.get("body", "") or "",
        )

    elif action in LABEL_ACTIONS and "issue" in event:
        issue = event["issue"]
        sync_issue_label_to_prs(
            repo=repo,
            issue_number=issue["number"],
            action=action,
            label=event["label"]["name"],
        )

    elif action in ["opened", "edited"] and "pull_request" in event:
        pr = event["pull_request"]

        # Add needs-review to all PRs when opened
        if action == "opened":
            add_label(repo, pr["number"], "needs-review")

        issue_nums = linked_issue_numbers(pr.get("body", "") or "")
        for issue_num in issue_nums:
            labels = [
                label["name"]
                for label in issue_labels(repo, issue_num)
            ]
            add_label(repo, pr["number"], *labels)

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
