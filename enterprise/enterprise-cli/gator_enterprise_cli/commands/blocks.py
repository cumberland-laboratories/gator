"""blocks commands — list, transcript, session reconstruction."""

from gator_enterprise_cli.output import print_json, print_kv, print_table


def register(subparsers):
    """Register blocks subcommands."""
    blocks_parser = subparsers.add_parser("blocks", help="Session block operations")
    blocks_sub = blocks_parser.add_subparsers(dest="blocks_command")

    ls = blocks_sub.add_parser("list", help="List session blocks for a repo")
    ls.add_argument("repo_id", help="Repository UUID")

    tx = blocks_sub.add_parser("transcript", help="Fetch transcript for a commit")
    tx.add_argument("commit_id", help="Commit UUID")


def handle(args, client):
    """Handle blocks commands."""
    if args.blocks_command == "list":
        data = client.get(f"/api/v1/views/repos/{args.repo_id}/blocks")
        if args.json:
            print_json(data)
        else:
            rows = [
                [
                    b["commit_sha"][:8],
                    b.get("vendor", "—"),
                    str(b.get("turn_count", "—")),
                    b.get("capture_quality", "—"),
                    b.get("machine_id", "—") or "—",
                    b.get("committed_at", "—")[:10] if b.get("committed_at") else "—",
                ]
                for b in data.get("blocks", [])
            ]
            print_table(["Commit", "Vendor", "Turns", "Quality", "Machine", "Date"], rows)
            total = data.get("pagination", {}).get("total", 0)
            if total > len(rows):
                print(f"\n({len(rows)} of {total} blocks shown)")

    elif args.blocks_command == "transcript":
        data = client.get(f"/api/v1/views/commits/{args.commit_id}/transcript")
        if args.json:
            print_json(data)
        else:
            print(f"Commit:  {data.get('commit_sha', '—')}")
            print(f"Vendor:  {data.get('vendor', '—')}")
            print(f"Quality: {data.get('capture_quality', '—')}")
            print(f"Turns:   {data.get('turn_count', 0)}")
            print()
            for turn in data.get("turns", []):
                role = turn.get("role", "unknown")
                content = turn.get("content", "")
                ts = turn.get("timestamp", "")
                prefix = {"user": "USER", "assistant": "ASST", "tool_result": "TOOL"}.get(role, role.upper())
                # Show first 200 chars of each turn
                preview = content[:200] + ("..." if len(content) > 200 else "")
                print(f"[{prefix}] {ts}")
                print(f"  {preview}")
                print()
