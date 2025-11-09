
import argparse, requests, os, time

def read_file(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capability", required=True, choices=["code_quality","summarize_code"])
    parser.add_argument("--file", required=True, help="Path to a Python file")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    code = read_file(args.file)
    payload = {
        "capability": args.capability,
        "inputs": {"code": code, "filename": os.path.basename(args.file)},
        "policy": "safe-readonly"
    }

    r = requests.post(f"{args.api}/tasks", json=payload, timeout=30)
    r.raise_for_status()
    task_id = r.json()["task_id"]
    print("Submitted task:", task_id)

    # since server completes immediately, one poll is enough; keeping loop for clarity
    while True:
        s = requests.get(f"{args.api}/tasks/{task_id}", timeout=30).json()
        if s["status"] == "SUCCEEDED":
            print("Result:\n", s["result"])
            break
        time.sleep(0.5)

if __name__ == "__main__":
    main()
