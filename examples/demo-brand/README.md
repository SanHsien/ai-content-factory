# Demo brand

Run the exact offline demo from the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m ai_content_factory demo
```

The command writes deterministic artifacts and seven platform text files under
`examples/demo-brand/output/<run_id>/`. The platform-ready set is
`facebook`, `instagram`, `threads`, `tiktok`, `youtube`, `xiaohongshu`, and
`douyin`. It uses synthetic fixtures only. Approval stays a manual review
state and `REMOTE_WRITE` remains `0`.
