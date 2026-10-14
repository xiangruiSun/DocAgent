# Security policy

DocAgent is local software that reads repository content and may write project documentation when an agent follows the skill. It does not require network access, credentials, or telemetry.

Review the skill and bundled Python scripts before installation. The installer refuses to overwrite or remove directories it did not create. Git hooks installed by DocAgent are read-only checks and never rewrite documentation during a commit.

Report suspected command injection, unsafe path handling, destructive installation behavior, or trust-gate bypass privately to GitHub private vulnerability reporting at https://github.com/xiangruiSun/Doccanon_Agent/security/advisories/new. Do not include secrets or private repository content in a public issue.
