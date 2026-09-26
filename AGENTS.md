## WSL Sandbox Handling

- Run commands inside the normal sandbox by default.
- If a command invoked through `wsl.exe` fails with an error containing `E_ACCESSDENIED` from the WSL service, treat it as a Windows sandbox limitation.
- This includes errors such as `Wsl/Service/E_ACCESSDENIED`, `Wsl/EnumerateDistros/Service/E_ACCESSDENIED`, and other `Wsl/.../Service/E_ACCESSDENIED` variants.
- Do not retry the same WSL command inside the sandbox.
- Do not modify WSL, Windows services, permissions, ACLs, or system configuration for this sandbox error.
- Re-run only the failed WSL command once outside the sandbox using the normal escalation mechanism.
- If it still fails outside the sandbox, stop and report the actual error.
