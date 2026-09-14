{
  "schema_version": 1,
  "allowed_binaries": [
    "codimango", "git", "python", "python3", "bash", "sh", "jq", "grep", "rg", "sed", "awk", "wc", "sha256sum", "xcodebuild", "xcrun", "buck2", "meta", "tar", "unzip"
  ],
  "allowed_codimango_reads": [
    ["task", "show"],
    ["task", "comments"],
    ["task", "reviews"],
    ["task", "errors"],
    ["job", "list"],
    ["job", "review"],
    ["trial", "list"],
    ["trial", "artifacts"]
  ],
  "allowed_git_reads": ["clone", "status", "log", "show", "diff", "rev-parse", "ls-tree", "cat-file"],
  "allowed_meta_prefixes": ["codehub.", "search.knowledge", "skills.sdk load"],
  "forbidden_patterns": [
    "codimango task list",
    "codimango feedback",
    "codimango validate",
    "codimango bench validate",
    "git commit",
    "git push",
    "git reset --hard",
    "jf submit",
    "jf land",
    "gh pr create",
    "gh issue create",
    "meta google.chat",
    "meta google.gmail",
    "meta workplace.post",
    "curl -x post",
    "curl --request post"
  ]
}
