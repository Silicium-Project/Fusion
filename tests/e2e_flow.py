import subprocess
import time
import requests
import re
import sys
import os

def extract_peer_id(process):
    # Read lines until we find the peer id
    while True:
        line = process.stdout.readline()
        if not line:
            return None
        line_safe = line.strip().encode('ascii', errors='replace').decode('ascii')
        print(f"[P2P_NODE] {line_safe}")
        m = re.search(r"Local peer id: (\S+)", line_safe)
        if m:
            return m.group(1)

def main():
    print("Starting E2E Integration Test...")
    
    # Paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mock_raytracer_bat = os.path.join(base_dir, "tests", "mock_raytracer.bat")
    
    # 1. Start Compute Daemon
    print("Starting Compute Daemon...")
    compute_env = os.environ.copy()
    compute_env["SILICIUM_RAYTRACER_BIN"] = mock_raytracer_bat
    compute_proc = subprocess.Popen(
        ["cargo", "run", "--manifest-path", "Network/networked/compute_daemon/Cargo.toml"],
        env=compute_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # 2. Start Reputation Bridge
    print("Starting Reputation Bridge...")
    rep_proc = subprocess.Popen(
        ["cargo", "run", "--manifest-path", "Network/networked/reputation_bridge/Cargo.toml"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # 3. Start P2P Node 1 (Publisher)
    print("Starting P2P Node 1 (Publisher)...")
    env1 = os.environ.copy()
    env1["API_PORT"] = "9092"
    p2p_node1 = subprocess.Popen(
        ["cargo", "run", "--manifest-path", "Network/networked/p2p_node/Cargo.toml"],
        env=env1,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8"
    )
    peer_id_1 = extract_peer_id(p2p_node1)
    print(f"P2P Node 1 Peer ID: {peer_id_1}")
    
    # 4. Start P2P Node 2 (Worker)
    print("Starting P2P Node 2 (Worker)...")
    env2 = os.environ.copy()
    env2["API_PORT"] = "9093"
    p2p_node2 = subprocess.Popen(
        ["cargo", "run", "--manifest-path", "Network/networked/p2p_node/Cargo.toml"],
        env=env2,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8"
    )
    peer_id_2 = extract_peer_id(p2p_node2)
    print(f"P2P Node 2 Peer ID: {peer_id_2}")
    
    print("Waiting for services to initialize and mDNS discovery (15s)...")
    time.sleep(15)
    
    # We want Node 2 to process the task, and Node 1 is the one that emitted it.
    # When Node 2 receives it, `propagation_source` will be Node 1's peer ID.
    
    task_payload = {
        "task_id": "test-e2e-task-001",
        "scene_path": "dummy_scene.json",
        "output_path": "dummy_output.ppm",
        "seed": "random-seed-123"
    }
    
    print(f"Injecting task into P2P Node 1 (Port 9092)...")
    try:
        r = requests.post("http://127.0.0.1:9092/publish", json=task_payload)
        r.raise_for_status()
        print(f"Task injected: {r.text}")
    except Exception as e:
        print(f"Failed to inject task: {e}")
        cleanup([compute_proc, rep_proc, p2p_node1, p2p_node2])
        sys.exit(1)
        
    print("Waiting for task to propagate and be processed by Node 2 (10s)...")
    
    # Let's read some logs from Node 2 to see if it processes it
    import threading
    def print_logs(proc, prefix):
        while True:
            line = proc.stdout.readline()
            if not line: break
            line_safe = line.strip().encode('ascii', errors='replace').decode('ascii')
            print(f"[{prefix}] {line_safe}")
            
    t1 = threading.Thread(target=print_logs, args=(p2p_node1, "NODE_1"), daemon=True)
    t2 = threading.Thread(target=print_logs, args=(p2p_node2, "NODE_2"), daemon=True)
    t1.start()
    t2.start()

    time.sleep(10)
    
    # 5. Check reputation score for Node 1
    # When Node 2 processes the task coming from Node 1, it will send an observation for peer_id_1.
    print(f"Checking reputation score for Node 1 ({peer_id_1})...")
    try:
        r = requests.post("http://127.0.0.1:9091/reputation/score", json={"peer_id": peer_id_1})
        r.raise_for_status()
        data = r.json()
        print(f"Reputation data: {data}")
        if data.get("score", 0) > 0.5:
            print("E2E Test Passed! Reputation was successfully updated based on verified work.")
        else:
            print("Reputation did not increase. Score is still 0.5 or lower.")
            sys.exit(1)
    except Exception as e:
        print(f"Failed to get reputation: {e}")
        cleanup([compute_proc, rep_proc, p2p_node1, p2p_node2])
        sys.exit(1)
        
    print("Cleaning up processes...")
    cleanup([compute_proc, rep_proc, p2p_node1, p2p_node2])
    print("E2E flow completed.")

def cleanup(procs):
    for p in procs:
        p.terminate()
        
if __name__ == "__main__":
    main()
