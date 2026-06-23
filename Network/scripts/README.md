# Multi-machine P2P scripts

These scripts prepare a real LAN/multi-machine run.

## 1. Configure IPs

Copy the examples:

```powershell
copy .\config\orchestrator.env.example .\config\orchestrator.env
copy .\config\worker.env.example .\config\worker.env
copy .\config\verifier.env.example .\config\verifier.env
```

Replace:

- `SILICIUM_ORCHESTRATOR_HOST`
- `SILICIUM_NODE_ADVERTISE_HOST`
- `SILICIUM_WORKER_URL`
- `SILICIUM_VERIFIER_URL`
- `SILICIUM_ORCHESTRATOR_URL`

Never use `127.0.0.1` between different machines.

## 2. Open firewall ports

Run as Administrator on each Windows machine:

```powershell
.\scripts\open-firewall-ports.ps1
```

## 3. Start worker and verifier

On the worker machine:

```powershell
.\scripts\start-worker.cmd
```

On the verifier machine:

```powershell
.\scripts\start-verifier.cmd
```

## 4. Check connectivity

From the orchestrator machine:

```powershell
.\scripts\check-peer.cmd http://WORKER_IP:46101
.\scripts\check-peer.cmd http://VERIFIER_IP:46102
```

## 5. Run a real P2P raytracer job

On the orchestrator machine:

```powershell
.\scripts\run-raytracer-p2p-job.cmd
```

The job script starts the orchestrator node for that job, waits for compute and
verify peers, dispatches fragments by reputation, verifies, reassembles, then
optionally writes the Devnet trace.
