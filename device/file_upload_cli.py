import argparse
import os
import socket


DEFAULT_HOST = "192.168.3.10"
DEFAULT_PORT = 7000


def upload_file(host, port, file_path, remote_name=None):
    file_path = os.path.abspath(file_path)
    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    send_name = remote_name or os.path.basename(file_path)

    with open(file_path, "rb") as fp:
        data = fp.read()

    with socket.create_connection((host, port), timeout=10) as sock:
        sock.sendall((send_name + "\n").encode("utf-8"))
        sock.sendall(data)
        sock.shutdown(socket.SHUT_WR)

        resp = sock.recv(1024)
        if resp:
            print(resp.decode("utf-8", errors="replace").strip())
        else:
            print("no response")

# python3 /Users/admin/Desktop/Noon/device/file_upload_cli.py /path/to/local/file.py --host 192.168.0.10 --port 7000 --name main.py

def main():
    parser = argparse.ArgumentParser(description="Upload a file to NODE_A file server")
    parser.add_argument("file", help="local file path to upload")
    parser.add_argument("--host", default=DEFAULT_HOST, help="target host (default: %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="target port (default: %(default)s)")
    parser.add_argument("--name", help="remote filename override")
    args = parser.parse_args()

    upload_file(args.host, args.port, args.file, remote_name=args.name)


if __name__ == "__main__":
    main()
